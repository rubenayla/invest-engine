"""
US House Periodic Transaction Report (PTR) Fetcher.

Pipeline:
  1. Download bulk-year ZIP from disclosures-clerk.house.gov
  2. Parse XML index to get (politician, FilingType=P, DocID) tuples
  3. For each new DocID, fetch the PDF and extract trade rows

PDFs are issued by the House Clerk under
https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/<year>/<doc_id>.pdf

Senate eFD requires session/JS handling and is intentionally not covered here.
"""

from __future__ import annotations

import io
import logging
import re
import threading
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pypdf

logger = logging.getLogger(__name__)

USER_AGENT = 'InvestAnalyzer admin@example.com'
HOUSE_BULK_URL = 'https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip'
HOUSE_PDF_URL = 'https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf'

# Map common amount-band labels to (min, max) in dollars.
AMOUNT_BANDS: Dict[str, tuple] = {
    '$1,001 - $15,000': (1_001, 15_000),
    '$15,001 - $50,000': (15_001, 50_000),
    '$50,001 - $100,000': (50_001, 100_000),
    '$100,001 - $250,000': (100_001, 250_000),
    '$250,001 - $500,000': (250_001, 500_000),
    '$500,001 - $1,000,000': (500_001, 1_000_000),
    '$1,000,001 - $5,000,000': (1_000_001, 5_000_000),
    '$5,000,001 - $25,000,000': (5_000_001, 25_000_000),
    '$25,000,001 - $50,000,000': (25_000_001, 50_000_000),
    'Over $50,000,000': (50_000_001, None),
}

TICKER_RE = re.compile(r'\(([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\)')
DATE_RE = re.compile(r'(\d{2}/\d{2}/\d{4})')
TX_TYPE_RE = re.compile(r'\b([PSE])\b')  # P=Purchase, S=Sale (full), E=Exchange


class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter (mirrors insider_fetcher.py)."""

    def __init__(self, rate: float = 4.0, burst: int = 4):
        self.rate = rate
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self) -> None:
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


@dataclass
class PtrIndexEntry:
    doc_id: str
    politician_name: str
    state_district: Optional[str]
    year: int
    filing_date: str  # MM/DD/YYYY


def fetch_ptr_index(year: int, rate_limiter: TokenBucketRateLimiter) -> List[PtrIndexEntry]:
    """Download and parse the bulk-year XML index, returning only PTR entries."""
    rate_limiter.acquire()
    url = HOUSE_BULK_URL.format(year=year)
    req = Request(url, headers={'User-Agent': USER_AGENT})
    with urlopen(req, timeout=60) as resp:
        zip_bytes = resp.read()

    entries: List[PtrIndexEntry] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        xml_name = next((n for n in zf.namelist() if n.lower().endswith('.xml')), None)
        if not xml_name:
            logger.warning('No XML file in %s', url)
            return entries
        xml_bytes = zf.read(xml_name)

    root = ET.fromstring(xml_bytes)
    for member in root.findall('Member'):
        filing_type = (member.findtext('FilingType') or '').strip()
        if filing_type != 'P':  # P = Periodic Transaction Report
            continue
        doc_id = (member.findtext('DocID') or '').strip()
        if not doc_id:
            continue
        last = (member.findtext('Last') or '').strip()
        first = (member.findtext('First') or '').strip()
        suffix = (member.findtext('Suffix') or '').strip()
        name = f"{last}, {first}".strip(', ')
        if suffix:
            name = f'{name} {suffix}'
        entries.append(
            PtrIndexEntry(
                doc_id=doc_id,
                politician_name=name,
                state_district=(member.findtext('StateDst') or '').strip() or None,
                year=year,
                filing_date=(member.findtext('FilingDate') or '').strip(),
            )
        )
    return entries


def fetch_and_parse_ptr_pdf(
    entry: PtrIndexEntry,
    rate_limiter: TokenBucketRateLimiter,
) -> List[Dict[str, Any]]:
    """Download a single PTR PDF and extract trade rows."""
    rate_limiter.acquire()
    url = HOUSE_PDF_URL.format(year=entry.year, doc_id=entry.doc_id)
    req = Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urlopen(req, timeout=60) as resp:
            pdf_bytes = resp.read()
    except (HTTPError, URLError) as exc:
        logger.debug('PDF fetch failed %s: %s', url, exc)
        return []

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    except Exception as exc:
        logger.debug('PDF parse failed %s: %s', url, exc)
        return []

    return _extract_trades_from_text(text, entry)


def _extract_trades_from_text(text: str, entry: PtrIndexEntry) -> List[Dict[str, Any]]:
    """Heuristic line-based parser for PTR PDF text."""
    trades: List[Dict[str, Any]] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Trade rows in PTR PDFs typically span 2-3 lines; we scan a sliding window
    # joining lines until we find ticker + transaction type + dates + amount.
    i = 0
    while i < len(lines):
        # Take a 4-line window joined as one logical row
        window = ' '.join(lines[i:i + 4])
        ticker_match = TICKER_RE.search(window)
        if not ticker_match:
            i += 1
            continue

        ticker = ticker_match.group(1)
        # Skip windows that are clearly not a transaction row
        if ticker in {'ID', 'PTR', 'STOCK'}:
            i += 1
            continue

        tx_type = _find_tx_type(window, ticker_match.end())
        dates = DATE_RE.findall(window)
        if not tx_type or len(dates) < 2:
            i += 1
            continue

        amount_min, amount_max = _find_amount(window)
        if amount_min is None and amount_max is None:
            i += 1
            continue

        tx_date = _normalize_date(dates[0])
        disc_date = _normalize_date(dates[1])
        # Sanity rewind: PDFs occasionally have transaction year typo'd to
        # match the disclosure year. Disclosure must be on/after the trade.
        if tx_date > disc_date:
            tx_date = _rewind_year(tx_date)

        trades.append({
            'ticker': ticker,
            'politician_name': entry.politician_name,
            'party': None,  # Not in House XML; could enrich later
            'chamber': 'House',
            'state_district': entry.state_district,
            'transaction_date': tx_date,
            'disclosure_date': disc_date,
            'transaction_type': tx_type,
            'amount_min': amount_min,
            'amount_max': amount_max,
            'asset_description': window[:200],
            'doc_id': entry.doc_id,
            'source': 'house_clerk',
        })
        i += 2  # advance past this row (rows usually take ~2 lines)

    return _dedupe_trades(trades)


def _find_tx_type(window: str, after_pos: int) -> Optional[str]:
    """Locate P/S/E transaction-type marker after the ticker mention."""
    tail = window[after_pos:after_pos + 80]
    match = TX_TYPE_RE.search(tail)
    return match.group(1) if match else None


def _find_amount(window: str) -> tuple:
    for label, (lo, hi) in AMOUNT_BANDS.items():
        if label in window:
            return (lo, hi)
    return (None, None)


def _normalize_date(mdY: str) -> str:
    """Convert MM/DD/YYYY to YYYY-MM-DD."""
    try:
        m, d, y = mdY.split('/')
        return f'{int(y):04d}-{int(m):02d}-{int(d):02d}'
    except (ValueError, AttributeError):
        return mdY


def _rewind_year(iso_date: str) -> str:
    """Subtract 1 year from a YYYY-MM-DD string. Returns input on error."""
    try:
        y, m, d = iso_date.split('-')
        return f'{int(y) - 1:04d}-{m}-{d}'
    except (ValueError, AttributeError):
        return iso_date


def _dedupe_trades(trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    unique = []
    for t in trades:
        key = (t['ticker'], t['transaction_date'], t['transaction_type'], t['amount_min'])
        if key in seen:
            continue
        seen.add(key)
        unique.append(t)
    return unique
