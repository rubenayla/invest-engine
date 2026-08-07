"""
SEC EDGAR Form 4 Insider Transaction Fetcher

Fetches and parses Form 4 filings (insider trades) from SEC EDGAR.
SEC requirements: User-Agent header required, max 10 req/s.
"""

import gzip
import json
import logging
import threading
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

SEC_BASE = "https://data.sec.gov"
SEC_FULL_INDEX = "https://efts.sec.gov"
USER_AGENT = "InvestAnalyzer admin@example.com"

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
CIK_MAP_PATH = PROJECT_ROOT / "data" / "sec_edgar" / "raw" / "ticker_to_cik.json"


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter."""

    def __init__(self, rate: float = 8.0, burst: int = 8):
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until a token is available."""
        while True:
            with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            time.sleep(0.05)


def load_cik_map() -> Dict[str, str]:
    """Load ticker-to-CIK mapping, filling gaps from SEC's company_tickers.json."""
    cik_map: Dict[str, str] = {}

    if CIK_MAP_PATH.exists():
        try:
            raw = CIK_MAP_PATH.read_text()
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and all(isinstance(v, str) for v in parsed.values()):
                cik_map = parsed
        except (json.JSONDecodeError, ValueError):
            logger.warning("ticker_to_cik.json is corrupted, will fetch from SEC")

    if not cik_map:
        cik_map = _fetch_sec_company_tickers()

    return cik_map


def _fetch_sec_company_tickers() -> Dict[str, str]:
    """Download SEC's company_tickers.json and build ticker->CIK map."""
    url = "https://www.sec.gov/files/company_tickers.json"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        logger.error("Failed to fetch SEC company_tickers.json: %s", exc)
        return {}

    result = {}
    for entry in data.values():
        ticker = entry.get("ticker", "").upper()
        cik = entry.get("cik_str")
        if ticker and cik:
            result[ticker] = str(cik).zfill(10)
    return result


def _sec_get(url: str, rate_limiter: Optional[TokenBucketRateLimiter] = None,
             max_retries: int = 3) -> bytes:
    """GET from SEC EDGAR with rate limiting and retries."""
    if rate_limiter:
        rate_limiter.acquire()

    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"})

    for attempt in range(max_retries):
        try:
            with urlopen(req, timeout=30) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b'\x1f\x8b':
                    raw = gzip.GzipFile(fileobj=BytesIO(raw)).read()
                return raw
        except HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                wait = min(2 ** (attempt + 1), 16)
                logger.warning("SEC %d on %s, retry in %ds", exc.code, url, wait)
                time.sleep(wait)
                if rate_limiter:
                    rate_limiter.acquire()
                continue
            raise
        except (URLError, TimeoutError) as exc:
            if attempt < max_retries - 1:
                wait = min(2 ** (attempt + 1), 16)
                logger.warning("Network error on %s: %s, retry in %ds", url, exc, wait)
                time.sleep(wait)
                continue
            raise

    raise RuntimeError(f"Failed after {max_retries} retries: {url}")


def fetch_submissions(cik: str,
                      rate_limiter: Optional[TokenBucketRateLimiter] = None) -> Dict[str, Any]:
    """Fetch filing submissions for a CIK from EDGAR."""
    padded = cik.zfill(10)
    url = f"{SEC_BASE}/submissions/CIK{padded}.json"
    data = _sec_get(url, rate_limiter)
    return json.loads(data)


def extract_form4_filings(submissions: Dict[str, Any],
                          since_date: str = "2024-01-01",
                          max_filings: int = 20) -> List[Dict[str, str]]:
    """Extract Form 4 filings from submissions JSON, capped at max_filings most recent."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    filings = []
    for i, form in enumerate(forms):
        if form != "4":
            continue
        if i >= len(dates) or i >= len(accessions) or i >= len(primary_docs):
            break
        if dates[i] < since_date:
            continue
        filings.append({
            "filing_date": dates[i],
            "accession_number": accessions[i],
            "primary_document": primary_docs[i],
        })
        if len(filings) >= max_filings:
            break

    return filings


def fetch_form4_xml(cik: str, accession: str, primary_doc: str,
                    rate_limiter: Optional[TokenBucketRateLimiter] = None) -> str:
    """Fetch the actual Form 4 XML document."""
    cik_int = str(int(cik))  # Strip leading zeros for URL path
    acc_no_dash = accession.replace("-", "")
    # primary_doc may have an XSL prefix like "xslF345X05/filename.xml" — strip it
    bare_doc = primary_doc.split("/")[-1]
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_dash}/{bare_doc}"
    data = _sec_get(url, rate_limiter)
    return data.decode("utf-8", errors="replace")


def parse_form4_xml(xml_text: str, ticker: str, cik: str,
                    filing_date: str, accession: str) -> List[Dict[str, Any]]:
    """
    Parse Form 4 XML to extract non-derivative transactions.

    Returns list of transaction dicts ready for DB insertion.
    """
    transactions = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.debug("XML parse error for %s/%s: %s", ticker, accession, exc)
        return []

    # Reporter info
    reporter_name = ""
    reporter_title = ""
    owner = root.find(".//reportingOwner")
    if owner is not None:
        rid = owner.find("reportingOwnerId")
        if rid is not None:
            name_el = rid.find("rptOwnerName")
            if name_el is not None and name_el.text:
                reporter_name = name_el.text.strip()
        rel = owner.find("reportingOwnerRelationship")
        if rel is not None:
            for title_tag in ("officerTitle", "isDirector", "isOfficer", "isTenPercentOwner"):
                el = rel.find(title_tag)
                if el is not None and el.text:
                    if title_tag == "officerTitle":
                        reporter_title = el.text.strip()
                        break
                    elif el.text.strip() == "1" or el.text.strip().lower() == "true":
                        reporter_title = title_tag.replace("is", "")
                        break

    # Non-derivative transactions
    for txn in root.findall(".//nonDerivativeTransaction"):
        tx_type = _xml_text(txn, ".//transactionCoding/transactionCode")
        if not tx_type:
            continue

        shares_str = _xml_text(txn, ".//transactionAmounts/transactionShares/value")
        price_str = _xml_text(txn, ".//transactionAmounts/transactionPricePerShare/value")
        owned_str = _xml_text(txn, ".//postTransactionAmounts/sharesOwnedFollowingTransaction/value")
        tx_date_str = _xml_text(txn, ".//transactionDate/value")

        shares = _safe_float(shares_str)
        price = _safe_float(price_str)
        owned_after = _safe_float(owned_str)

        if shares is None or shares == 0:
            continue

        is_open_market = 1 if tx_type.upper() in ("P", "S") else 0

        transactions.append({
            "ticker": ticker,
            "cik": cik,
            "accession_number": accession,
            "filing_date": filing_date,
            "transaction_date": tx_date_str or filing_date,
            "reporter_name": reporter_name,
            "reporter_title": reporter_title,
            "transaction_type": tx_type.upper(),
            "shares": shares,
            "price_per_share": price,
            "shares_owned_after": owned_after,
            "is_open_market": is_open_market,
        })

    return transactions


def fetch_insider_data_for_ticker(
    ticker: str,
    cik: str,
    rate_limiter: Optional[TokenBucketRateLimiter] = None,
    since_date: str = "2024-01-01",
    known_accessions: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Full pipeline: fetch submissions -> extract Form 4s -> parse XML -> return transactions.

    Skips already-known accession numbers for incremental runs.
    """
    if known_accessions is None:
        known_accessions = set()

    submissions = fetch_submissions(cik, rate_limiter)
    filings = extract_form4_filings(submissions, since_date=since_date)

    all_transactions = []
    new_count = 0
    skipped = 0

    for filing in filings:
        acc = filing["accession_number"]
        if acc in known_accessions:
            skipped += 1
            continue

        primary_doc = filing["primary_document"]
        if not primary_doc.endswith(".xml"):
            continue

        try:
            xml_text = fetch_form4_xml(cik, acc, primary_doc, rate_limiter)
            txns = parse_form4_xml(
                xml_text, ticker, cik,
                filing["filing_date"], acc,
            )
            all_transactions.extend(txns)
            new_count += 1
        except Exception as exc:
            logger.warning("Failed to fetch/parse Form 4 for %s acc=%s: %s", ticker, acc, exc)

    logger.debug("%s: %d new filings parsed, %d skipped (known), %d transactions",
                 ticker, new_count, skipped, len(all_transactions))
    return all_transactions


def _xml_text(element: ET.Element, xpath: str) -> Optional[str]:
    """Safely extract text from an XML element."""
    el = element.find(xpath)
    if el is not None and el.text:
        return el.text.strip()
    return None


def _safe_float(val: Optional[str]) -> Optional[float]:
    """Safely convert string to float."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
