"""
SEC EDGAR 13D/13G Activist & Large Stake Fetcher

Fetches and parses SC 13D/13G filings (5%+ ownership stakes) from SEC EDGAR.
Reuses rate limiter and HTTP helpers from insider_fetcher.
"""

import json
import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Set

from .insider_fetcher import (
    TokenBucketRateLimiter,
    _sec_get,
    fetch_submissions,
)

logger = logging.getLogger(__name__)

FORM_13D_TYPES = {"SC 13D", "SC 13D/A"}
FORM_13G_TYPES = {"SC 13G", "SC 13G/A"}
ALL_13DG_TYPES = FORM_13D_TYPES | FORM_13G_TYPES


def extract_13d_filings(
    submissions: Dict[str, Any],
    since_date: str = "2024-01-01",
    max_filings: int = 30,
) -> List[Dict[str, str]]:
    """Extract SC 13D/13G filings from submissions JSON."""
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    filings = []
    for i, form in enumerate(forms):
        if form not in ALL_13DG_TYPES:
            continue
        if i >= len(dates) or i >= len(accessions) or i >= len(primary_docs):
            break
        if dates[i] < since_date:
            continue
        filings.append({
            "filing_date": dates[i],
            "accession_number": accessions[i],
            "primary_document": primary_docs[i],
            "form_type": form,
        })
        if len(filings) >= max_filings:
            break

    return filings


def fetch_13d_xml(
    cik: str,
    accession: str,
    primary_doc: str,
    rate_limiter: Optional[TokenBucketRateLimiter] = None,
) -> str:
    """Fetch the 13D/13G filing document."""
    cik_int = str(int(cik))
    acc_no_dash = accession.replace("-", "")
    bare_doc = primary_doc.split("/")[-1]
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_no_dash}/{bare_doc}"
    data = _sec_get(url, rate_limiter)
    return data.decode("utf-8", errors="replace")


def parse_13d_xml(
    xml_text: str,
    ticker: str,
    cik: str,
    filing_date: str,
    accession: str,
    form_type: str,
) -> List[Dict[str, Any]]:
    """
    Parse 13D/13G XML to extract stake information.

    These filings vary in structure — XML, SGML, or HTML wrapped.
    We attempt XML parse first, then fall back to text extraction.
    """
    is_activist = 1 if form_type in FORM_13D_TYPES else 0
    stakes = []

    # Try XML parsing first
    try:
        root = ET.fromstring(xml_text)
        stakes = _parse_xml_structured(root, ticker, cik, filing_date, accession, form_type, is_activist)
        if stakes:
            return stakes
    except ET.ParseError:
        pass

    # Fall back to text extraction for SGML/HTML filings
    stakes = _parse_text_fallback(xml_text, ticker, cik, filing_date, accession, form_type, is_activist)
    return stakes


def _parse_xml_structured(
    root: ET.Element,
    ticker: str,
    cik: str,
    filing_date: str,
    accession: str,
    form_type: str,
    is_activist: int,
) -> List[Dict[str, Any]]:
    """Parse structured XML 13D/13G filing."""
    stakes = []

    # Try common XML paths for 13D/13G
    holder_name = _xml_text_any(root, [
        ".//reportingOwner//rptOwnerName",
        ".//filedBy//companyName",
        ".//nameOfReportingPerson",
        ".//REPORTING-OWNER//COMPANY-DATA//CONFORMED-NAME",
    ]) or ""

    shares_str = _xml_text_any(root, [
        ".//aggregateAmountBeneficiallyOwned",
        ".//shrsOrPrnAmt//sshPrnamt",
    ])
    pct_str = _xml_text_any(root, [
        ".//percentOfClass",
    ])
    purpose = _xml_text_any(root, [
        ".//purposeOfTransaction",
        ".//ITEM4",
        ".//PURPOSE",
    ]) or ""

    shares = _safe_float(shares_str)
    pct = _safe_float(pct_str)

    if holder_name:
        stakes.append({
            "ticker": ticker,
            "cik": cik,
            "accession_number": accession,
            "filing_date": filing_date,
            "holder_name": holder_name.strip(),
            "form_type": form_type,
            "shares_held": shares,
            "percent_of_class": pct,
            "purpose_text": purpose[:500].strip() if purpose else "",
            "is_activist": is_activist,
        })

    return stakes


def _parse_text_fallback(
    text: str,
    ticker: str,
    cik: str,
    filing_date: str,
    accession: str,
    form_type: str,
    is_activist: int,
) -> List[Dict[str, Any]]:
    """Extract stake info from plain text / SGML filings via regex-like patterns."""
    import re

    holder_name = ""
    shares = None
    pct = None
    purpose = ""

    # Try to find reporting person name
    name_patterns = [
        r"NAME OF REPORTING PERSONS?\s*[:\n]\s*(.+)",
        r"FILED BY:\s*\n\s*COMPANY.*?CONFORMED NAME:\s*(.+)",
    ]
    for pat in name_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            holder_name = m.group(1).strip()
            break

    # Try to find percentage
    pct_patterns = [
        r"PERCENT OF CLASS.*?:\s*([\d.]+)",
        r"(\d{1,3}\.\d{1,2})\s*%\s*(?:of class|of the class)",
    ]
    for pat in pct_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            pct = _safe_float(m.group(1))
            break

    # Try to find shares
    shares_patterns = [
        r"AGGREGATE AMOUNT.*?:\s*([\d,]+)",
    ]
    for pat in shares_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            shares = _safe_float(m.group(1).replace(",", ""))
            break

    # Purpose
    purpose_m = re.search(r"ITEM 4[.\s]*PURPOSE.*?\n(.+?)(?:\n\s*ITEM|\Z)", text, re.IGNORECASE | re.DOTALL)
    if purpose_m:
        purpose = purpose_m.group(1).strip()[:500]

    if holder_name or pct is not None:
        return [{
            "ticker": ticker,
            "cik": cik,
            "accession_number": accession,
            "filing_date": filing_date,
            "holder_name": holder_name or "Unknown",
            "form_type": form_type,
            "shares_held": shares,
            "percent_of_class": pct,
            "purpose_text": purpose,
            "is_activist": is_activist,
        }]

    return []


def fetch_activist_data_for_ticker(
    ticker: str,
    cik: str,
    rate_limiter: Optional[TokenBucketRateLimiter] = None,
    since_date: str = "2024-01-01",
    known_accessions: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Full pipeline: fetch submissions -> extract 13D/13G -> parse -> return stakes.

    Skips already-known accession numbers for incremental runs.
    """
    if known_accessions is None:
        known_accessions = set()

    submissions = fetch_submissions(cik, rate_limiter)
    filings = extract_13d_filings(submissions, since_date=since_date)

    all_stakes = []
    new_count = 0
    skipped = 0

    for filing in filings:
        acc = filing["accession_number"]
        if acc in known_accessions:
            skipped += 1
            continue

        primary_doc = filing["primary_document"]
        try:
            doc_text = fetch_13d_xml(cik, acc, primary_doc, rate_limiter)
            stakes = parse_13d_xml(
                doc_text, ticker, cik,
                filing["filing_date"], acc, filing["form_type"],
            )
            all_stakes.extend(stakes)
            new_count += 1
        except Exception as exc:
            logger.warning("Failed to fetch/parse 13D/G for %s acc=%s: %s", ticker, acc, exc)

    logger.debug(
        "%s: %d new 13D/G filings parsed, %d skipped, %d stakes",
        ticker, new_count, skipped, len(all_stakes),
    )
    return all_stakes


def _xml_text_any(element: ET.Element, xpaths: List[str]) -> Optional[str]:
    """Try multiple xpaths and return first match text."""
    for xpath in xpaths:
        el = element.find(xpath)
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
