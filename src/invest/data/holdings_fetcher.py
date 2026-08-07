"""
SEC EDGAR 13F Institutional Holdings Fetcher

Fetches and parses 13F-HR filings (quarterly institutional holdings) from SEC EDGAR.
Iterates over a curated list of "smart money" fund CIKs.
Reuses rate limiter and HTTP helpers from insider_fetcher.
"""

import json
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .insider_fetcher import (
    TokenBucketRateLimiter,
    _sec_get,
    fetch_submissions,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
SMART_MONEY_PATH = PROJECT_ROOT / "data" / "sec_edgar" / "smart_money_funds.json"
CUSIP_MAP_PATH = PROJECT_ROOT / "data" / "sec_edgar" / "cusip_to_ticker.json"

# 13F information table XML namespace
NS_13F = "http://www.sec.gov/edgar/document/thirteenf/informationtable"


def load_smart_money_funds() -> List[Dict[str, str]]:
    """Load curated list of smart money funds from JSON."""
    if not SMART_MONEY_PATH.exists():
        logger.error("Smart money funds file not found: %s", SMART_MONEY_PATH)
        return []
    try:
        return json.loads(SMART_MONEY_PATH.read_text())
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error("Failed to parse smart_money_funds.json: %s", exc)
        return []


def load_cusip_map() -> Dict[str, str]:
    """Load CUSIP -> ticker mapping. Returns empty dict if not built yet."""
    if not CUSIP_MAP_PATH.exists():
        return {}
    try:
        return json.loads(CUSIP_MAP_PATH.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}


def save_cusip_map(cusip_map: Dict[str, str]) -> None:
    """Save CUSIP -> ticker mapping."""
    CUSIP_MAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    CUSIP_MAP_PATH.write_text(json.dumps(cusip_map, indent=2, sort_keys=True))


def extract_13f_filings(
    submissions: Dict[str, Any],
    max_filings: int = 4,
) -> List[Dict[str, str]]:
    """Extract 13F-HR filings from submissions JSON (most recent N quarters)."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    filings = []
    for i, form in enumerate(forms):
        if form != "13F-HR":
            continue
        if i >= len(dates) or i >= len(accessions) or i >= len(primary_docs):
            break
        filings.append({
            "filing_date": dates[i],
            "accession_number": accessions[i],
            "primary_document": primary_docs[i],
        })
        if len(filings) >= max_filings:
            break

    return filings


def _find_info_table_doc(
    cik: str,
    accession: str,
    rate_limiter: Optional[TokenBucketRateLimiter] = None,
) -> Optional[str]:
    """Find the information table XML document within a 13F filing index."""
    cik_int = str(int(cik))
    acc_no_dash = accession.replace("-", "")
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_dash}/index.json"

    try:
        data = _sec_get(index_url, rate_limiter)
        index_data = json.loads(data)
        items = index_data.get("directory", {}).get("item", [])
        for item in items:
            name = item.get("name", "").lower()
            if "infotable" in name and name.endswith(".xml"):
                return item["name"]
    except Exception as exc:
        logger.debug("Failed to fetch filing index for %s/%s: %s", cik, accession, exc)

    return None


def fetch_holdings_xml(
    fund_cik: str,
    accession: str,
    primary_doc: str,
    rate_limiter: Optional[TokenBucketRateLimiter] = None,
) -> str:
    """Fetch the 13F information table XML."""
    cik_int = str(int(fund_cik))
    acc_no_dash = accession.replace("-", "")

    # The primary doc is often the cover page, not the holdings table.
    # Try to find the actual infotable document.
    info_doc = _find_info_table_doc(fund_cik, accession, rate_limiter)
    doc_name = info_doc or primary_doc.split("/")[-1]

    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_dash}/{doc_name}"
    data = _sec_get(url, rate_limiter)
    return data.decode("utf-8", errors="replace")


def parse_holdings_xml(
    xml_text: str,
    fund_name: str,
    fund_cik: str,
    filing_date: str,
    cusip_map: Dict[str, str],
) -> List[Dict[str, Any]]:
    """
    Parse 13F information table XML to extract holdings.

    Returns list of holding dicts ready for DB insertion.
    """
    holdings = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.debug("XML parse error for 13F %s/%s: %s", fund_name, filing_date, exc)
        return []

    # Determine quarter from filing date (e.g., "2025-11-14" -> "2025Q3")
    quarter = _filing_date_to_quarter(filing_date)

    # Try namespaced and non-namespaced paths
    info_tables = root.findall(f".//{{{NS_13F}}}infoTable")
    if not info_tables:
        info_tables = root.findall(".//infoTable")

    for entry in info_tables:
        issuer = _ns_text(entry, "nameOfIssuer") or ""
        cusip = _ns_text(entry, "cusip") or ""
        shares_str = _ns_text(entry, "shrsOrPrnAmt/sshPrnamt") or _ns_text(entry, "sshPrnamt")
        value_str = _ns_text(entry, "value")

        shares = _safe_float(shares_str)
        value_usd = _safe_float(value_str)

        # 13F values are reported in thousands
        if value_usd is not None:
            value_usd *= 1000

        ticker = cusip_map.get(cusip, "")

        holdings.append({
            "fund_name": fund_name,
            "fund_cik": fund_cik,
            "filing_date": filing_date,
            "quarter": quarter,
            "cusip": cusip,
            "ticker": ticker,
            "issuer_name": issuer.strip(),
            "shares": shares,
            "value_usd": value_usd,
        })

    return holdings


def fetch_holdings_for_fund(
    fund_name: str,
    fund_cik: str,
    rate_limiter: Optional[TokenBucketRateLimiter] = None,
    known_accessions: Optional[Set[str]] = None,
    cusip_map: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """
    Full pipeline for one fund: fetch submissions -> extract 13Fs -> parse holdings.
    """
    if known_accessions is None:
        known_accessions = set()
    if cusip_map is None:
        cusip_map = load_cusip_map()

    submissions = fetch_submissions(fund_cik, rate_limiter)
    filings = extract_13f_filings(submissions)

    all_holdings = []
    new_count = 0
    skipped = 0

    for filing in filings:
        acc = filing["accession_number"]
        if acc in known_accessions:
            skipped += 1
            continue

        try:
            xml_text = fetch_holdings_xml(
                fund_cik, acc, filing["primary_document"], rate_limiter,
            )
            holdings = parse_holdings_xml(
                xml_text, fund_name, fund_cik,
                filing["filing_date"], cusip_map,
            )
            all_holdings.extend(holdings)
            new_count += 1
        except Exception as exc:
            logger.warning("Failed to fetch/parse 13F for %s acc=%s: %s", fund_name, acc, exc)

    logger.debug(
        "%s: %d new 13F filings parsed, %d skipped, %d holdings",
        fund_name, new_count, skipped, len(all_holdings),
    )
    return all_holdings


def _filing_date_to_quarter(filing_date: str) -> str:
    """Convert filing date to approximate reporting quarter (e.g., '2025Q3').

    13F filings are due 45 days after quarter end:
    Q1 (Mar 31) -> filed by May 15
    Q2 (Jun 30) -> filed by Aug 14
    Q3 (Sep 30) -> filed by Nov 14
    Q4 (Dec 31) -> filed by Feb 14
    """
    try:
        month = int(filing_date.split("-")[1])
        year = int(filing_date.split("-")[0])
        if month <= 2:
            return f"{year - 1}Q4"
        elif month <= 5:
            return f"{year}Q1"
        elif month <= 8:
            return f"{year}Q2"
        elif month <= 11:
            return f"{year}Q3"
        else:
            return f"{year}Q4"
    except (IndexError, ValueError):
        return ""


def _ns_text(element: ET.Element, tag: str) -> Optional[str]:
    """Find text with or without 13F namespace."""
    # Try with namespace
    el = element.find(f"{{{NS_13F}}}{tag}")
    if el is None:
        # Try nested namespace path
        parts = tag.split("/")
        if len(parts) == 2:
            parent = element.find(f"{{{NS_13F}}}{parts[0]}")
            if parent is not None:
                el = parent.find(f"{{{NS_13F}}}{parts[1]}")
    if el is None:
        # Try without namespace
        el = element.find(tag)
    if el is None and "/" in tag:
        parts = tag.split("/")
        parent = element.find(parts[0])
        if parent is not None:
            el = parent.find(parts[1])
    if el is not None and el.text:
        return el.text.strip()
    return None


def _safe_float(val: Optional[str]) -> Optional[float]:
    """Safely convert string to float."""
    if val is None:
        return None
    try:
        return float(val.replace(",", ""))
    except (ValueError, TypeError):
        return None
