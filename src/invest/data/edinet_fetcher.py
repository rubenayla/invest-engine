"""
EDINET (Japan FSA) Large Shareholding Report Fetcher

Fetches 大量保有報告書 (large shareholding reports, 5%+ stakes) for Japanese equities
from the EDINET API v2. Free registration at https://api.edinet-fsa.go.jp.

Requires EDINET_API_KEY environment variable.
"""

import csv
import io
import json
import logging
import os
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

EDINET_API_BASE = "https://api.edinet-fsa.go.jp/api/v2"
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
EDINET_MAP_PATH = PROJECT_ROOT / "data" / "edinet" / "ticker_to_edinet.json"


def load_edinet_map() -> Dict[str, str]:
    """Load ticker -> EDINET code mapping for Japanese stocks."""
    if not EDINET_MAP_PATH.exists():
        return {}
    try:
        return json.loads(EDINET_MAP_PATH.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}


def _edinet_get(url: str, api_key: str, max_retries: int = 3) -> bytes:
    """GET from EDINET API with API key and retries."""
    headers = {
        "Ocp-Apim-Subscription-Key": api_key,
        "Accept": "application/json",
    }
    req = Request(url, headers=headers)

    for attempt in range(max_retries):
        try:
            with urlopen(req, timeout=30) as resp:
                return resp.read()
        except HTTPError as exc:
            if exc.code == 429 or exc.code >= 500:
                wait = min(2 ** (attempt + 1), 16)
                logger.warning("EDINET %d on %s, retry in %ds", exc.code, url, wait)
                time.sleep(wait)
                continue
            raise
        except (URLError, TimeoutError) as exc:
            if attempt < max_retries - 1:
                wait = min(2 ** (attempt + 1), 16)
                logger.warning("Network error on %s: %s, retry in %ds", url, exc, wait)
                time.sleep(wait)
                continue
            raise

    raise RuntimeError(f"EDINET: Failed after {max_retries} retries: {url}")


def search_large_shareholding(
    api_key: str,
    from_date: str,
    to_date: str,
) -> List[Dict[str, Any]]:
    """
    Search EDINET for large shareholding reports (docTypeCode 350/360).

    Parameters
    ----------
    api_key : str
        EDINET API subscription key
    from_date : str
        Start date (YYYY-MM-DD)
    to_date : str
        End date (YYYY-MM-DD)

    Returns
    -------
    List of document metadata dicts with docID, filerName, etc.
    """
    # EDINET documents.json lists documents filed on a given date.
    # docTypeCode: 350 = 大量保有報告書, 360 = 変更報告書 (change report)
    all_docs = []

    from datetime import datetime, timedelta
    current = datetime.strptime(from_date, "%Y-%m-%d")
    end = datetime.strptime(to_date, "%Y-%m-%d")

    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        url = f"{EDINET_API_BASE}/documents.json?date={date_str}&type=2"

        try:
            data = _edinet_get(url, api_key)
            result = json.loads(data)
            docs = result.get("results", [])

            for doc in docs:
                doc_type = doc.get("docTypeCode")
                if doc_type in ("350", "360"):
                    all_docs.append(doc)

        except Exception as exc:
            logger.debug("EDINET search failed for %s: %s", date_str, exc)

        current += timedelta(days=1)
        time.sleep(0.5)  # Be gentle with rate

    return all_docs


def fetch_document_content(
    doc_id: str,
    api_key: str,
) -> Optional[str]:
    """
    Download EDINET document and extract CSV/text content.

    Returns the document content as text, or None on failure.
    """
    url = f"{EDINET_API_BASE}/documents/{doc_id}?type=5"  # type=5 = CSV

    try:
        data = _edinet_get(url, api_key)

        # EDINET returns a zip file containing CSV files
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for name in zf.namelist():
                    if name.endswith(".csv"):
                        return zf.read(name).decode("utf-8", errors="replace")
        except zipfile.BadZipFile:
            # Might be raw text
            return data.decode("utf-8", errors="replace")

    except Exception as exc:
        logger.debug("Failed to fetch EDINET doc %s: %s", doc_id, exc)

    return None


def parse_shareholding_report(
    doc: Dict[str, Any],
    csv_content: Optional[str],
    ticker: str,
) -> Optional[Dict[str, Any]]:
    """
    Parse a large shareholding report.

    Uses metadata from the document listing and optionally CSV content
    for detailed holdings data.
    """
    doc_id = doc.get("docID", "")
    filer_name = doc.get("filerName", "")
    submit_date = doc.get("submitDateTime", "")[:10]  # YYYY-MM-DD
    doc_type_code = doc.get("docTypeCode", "")

    report_type = "initial" if doc_type_code == "350" else "change"

    # Try to extract shares and percentage from CSV if available
    shares_held = None
    percent_of_class = None
    purpose = ""

    if csv_content:
        try:
            reader = csv.reader(io.StringIO(csv_content))
            for row in reader:
                row_text = ",".join(row).lower()
                if "保有割合" in row_text or "percent" in row_text:
                    for cell in row:
                        try:
                            val = float(cell.replace("%", "").strip())
                            if 0 < val < 100:
                                percent_of_class = val
                                break
                        except ValueError:
                            continue
                if "保有株券等の数" in row_text or "shares" in row_text:
                    for cell in row:
                        try:
                            val = float(cell.replace(",", "").strip())
                            if val > 0:
                                shares_held = val
                                break
                        except ValueError:
                            continue
                if "保有目的" in row_text or "purpose" in row_text:
                    purpose = " ".join(row[1:]).strip()[:500]
        except Exception:
            pass

    if not filer_name and not doc_id:
        return None

    return {
        "ticker": ticker,
        "edinet_code": doc.get("edinetCode", ""),
        "doc_id": doc_id,
        "report_date": submit_date,
        "holder_name": filer_name,
        "shares_held": shares_held,
        "percent_of_class": percent_of_class,
        "purpose": purpose,
        "report_type": report_type,
    }


def fetch_japan_stakes_for_ticker(
    ticker: str,
    edinet_code: str,
    api_key: str,
    since_date: str,
    to_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Full pipeline: search EDINET -> filter by EDINET code -> parse reports.
    """
    if to_date is None:
        from datetime import datetime
        to_date = datetime.utcnow().strftime("%Y-%m-%d")

    docs = search_large_shareholding(api_key, since_date, to_date)

    # Filter docs related to this company's EDINET code
    relevant = [d for d in docs if d.get("edinetCode") == edinet_code
                or edinet_code in str(d.get("docDescription", ""))]

    stakes = []
    for doc in relevant:
        csv_content = fetch_document_content(doc.get("docID", ""), api_key)
        parsed = parse_shareholding_report(doc, csv_content, ticker)
        if parsed:
            stakes.append(parsed)

    logger.debug("%s: found %d large shareholding reports", ticker, len(stakes))
    return stakes
