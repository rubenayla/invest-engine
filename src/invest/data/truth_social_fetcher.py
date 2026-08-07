"""
Truth Social fetcher (Mastodon-compatible API) + lightweight NER.

Source endpoint:
    https://truthsocial.com/api/v1/accounts/<account_id>/statuses

Response is a JSON array of status objects with fields including:
- id        : status id (string)
- created_at: ISO-8601 timestamp
- content   : HTML body (with <p>, emoji shortcodes, etc.)

We strip HTML, run regex-and-dictionary NER over the plain text to extract
tickers / sectors / country tariff-targets, and return structured dicts
ready for the database upsert.

No spaCy / heavy ML — keep dependency footprint minimal.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Donald Trump's Truth Social account id (Mastodon-compatible numeric id).
# Source: public timeline at https://truthsocial.com/@realDonaldTrump
TRUMP_ACCOUNT_ID = '107780257626128497'
TRUTH_SOCIAL_API = 'https://truthsocial.com/api/v1/accounts/{account_id}/statuses'

# Polling cadence — be polite to the public API.
POLL_INTERVAL_SECONDS = 60

# Truth Social rejects bot-like User-Agents with 403. A common-browser UA
# is required for the public timeline endpoint. (Empirically verified
# 2026-04-30.)
DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'application/json',
}

# ── NER dictionaries ──────────────────────────────────────────────────────

# Cashtag pattern: $TICKER, 1-5 alphanumeric chars (digits allowed for
# Asian listings like $7203.T), optional .XX exchange suffix.
# Must contain at least one letter to avoid grabbing "$5" or "$1000".
# Bounded by a non-letter/digit on the right so $AAPL5 doesn't match.
CASHTAG_RE = re.compile(
    r'\$([A-Z0-9]{1,5}(?:\.[A-Z]{1,3})?)(?![A-Za-z0-9])'
)

# Hand-rolled fallback alias dict — used when DB is down or to supplement
# noisy long_name strings. Lowercased keys.
FALLBACK_TICKER_ALIASES: Dict[str, str] = {
    'apple': 'AAPL',
    'microsoft': 'MSFT',
    'google': 'GOOGL',
    'alphabet': 'GOOGL',
    'amazon': 'AMZN',
    'meta': 'META',
    'facebook': 'META',
    'nvidia': 'NVDA',
    'tesla': 'TSLA',
    'intel': 'INTC',
    'amd': 'AMD',
    'broadcom': 'AVGO',
    'qualcomm': 'QCOM',
    'taiwan semiconductor': 'TSM',
    'tsmc': 'TSM',
    'asml': 'ASML',
    'micron': 'MU',
    'boeing': 'BA',
    'lockheed': 'LMT',
    'lockheed martin': 'LMT',
    'raytheon': 'RTX',
    'northrop': 'NOC',
    'general dynamics': 'GD',
    'palantir': 'PLTR',
    'exxon': 'XOM',
    'exxon mobil': 'XOM',
    'chevron': 'CVX',
    'occidental': 'OXY',
    'conocophillips': 'COP',
    'shell': 'SHEL',
    'bp': 'BP',
    'jpmorgan': 'JPM',
    'jp morgan': 'JPM',
    'goldman sachs': 'GS',
    'morgan stanley': 'MS',
    'bank of america': 'BAC',
    'wells fargo': 'WFC',
    'citigroup': 'C',
    'citi': 'C',
    'pfizer': 'PFE',
    'moderna': 'MRNA',
    'eli lilly': 'LLY',
    'merck': 'MRK',
    'johnson & johnson': 'JNJ',
    'bristol myers': 'BMY',
    'novo nordisk': 'NVO',
    'walmart': 'WMT',
    'costco': 'COST',
    'home depot': 'HD',
    'mcdonald': 'MCD',
    'mcdonalds': 'MCD',
    'starbucks': 'SBUX',
    'coca-cola': 'KO',
    'coca cola': 'KO',
    'pepsi': 'PEP',
    'pepsico': 'PEP',
    'disney': 'DIS',
    'netflix': 'NFLX',
    'ford': 'F',
    'general motors': 'GM',
    'gm': 'GM',
    'rivian': 'RIVN',
    'lucid': 'LCID',
    'us steel': 'X',
    'u.s. steel': 'X',
    'nucor': 'NUE',
    'cleveland-cliffs': 'CLF',
    'cleveland cliffs': 'CLF',
    'caterpillar': 'CAT',
    'deere': 'DE',
    'john deere': 'DE',
    'sqm': 'SQM',
    'albemarle': 'ALB',
    'first solar': 'FSLR',
    'enphase': 'ENPH',
    'sunrun': 'RUN',
    'coinbase': 'COIN',
    'block': 'SQ',
    'paypal': 'PYPL',
    'visa': 'V',
    'mastercard': 'MA',
    'truth social': 'DJT',
    'trump media': 'DJT',
    'itochu': '8001.T',
    'mitsubishi corp': '8058.T',
    'mitsui': '8031.T',
    'sumitomo': '8053.T',
    'marubeni': '8002.T',
    'toyota': '7203.T',
    'sony': '6758.T',
    'nintendo': '7974.T',
    'softbank': '9984.T',
}

# Sector keyword dictionary. Values are canonical sector names; keys are
# lowercased trigger phrases. Order matters for longest-match preference.
SECTOR_KEYWORDS: Dict[str, str] = {
    'semiconductor': 'semiconductors',
    'semiconductors': 'semiconductors',
    'chip industry': 'semiconductors',
    'chips act': 'semiconductors',
    'oil': 'oil',
    'crude oil': 'oil',
    'gasoline': 'oil',
    'opec': 'oil',
    'drilling': 'oil',
    'pipeline': 'oil',
    'natural gas': 'oil',
    'defense': 'defense',
    'military': 'defense',
    'pentagon': 'defense',
    'weapons': 'defense',
    'pharmaceutical': 'pharma',
    'pharma': 'pharma',
    'drug prices': 'pharma',
    'big pharma': 'pharma',
    'banks': 'banks',
    'banking': 'banks',
    'wall street': 'banks',
    'crypto': 'crypto',
    'bitcoin': 'crypto',
    'btc': 'crypto',
    'ethereum': 'crypto',
    'auto industry': 'autos',
    'automakers': 'autos',
    'automaker': 'autos',
    'electric vehicle': 'autos',
    'ev makers': 'autos',
    'steel': 'steel',
    'aluminum': 'steel',
    'aluminium': 'steel',
    'tariffs on steel': 'steel',
    'artificial intelligence': 'AI',
    ' ai ': 'AI',
    'ai chips': 'AI',
    'data center': 'AI',
    'data centers': 'AI',
}

# Country / nationality dictionary. Values are canonical country names;
# keys are lowercased trigger phrases (both noun + adjective forms).
# Top-30 trading partners + tariff-priority targets.
COUNTRY_KEYWORDS: Dict[str, str] = {
    'china': 'China',
    'chinese': 'China',
    'mexico': 'Mexico',
    'mexican': 'Mexico',
    'canada': 'Canada',
    'canadian': 'Canada',
    'japan': 'Japan',
    'japanese': 'Japan',
    'germany': 'Germany',
    'german': 'Germany',
    'south korea': 'South Korea',
    'korean': 'South Korea',
    'korea': 'South Korea',
    'taiwan': 'Taiwan',
    'taiwanese': 'Taiwan',
    'india': 'India',
    'indian': 'India',
    'vietnam': 'Vietnam',
    'vietnamese': 'Vietnam',
    'united kingdom': 'United Kingdom',
    'britain': 'United Kingdom',
    'british': 'United Kingdom',
    'france': 'France',
    'french': 'France',
    'italy': 'Italy',
    'italian': 'Italy',
    'netherlands': 'Netherlands',
    'dutch': 'Netherlands',
    'switzerland': 'Switzerland',
    'swiss': 'Switzerland',
    'ireland': 'Ireland',
    'irish': 'Ireland',
    'brazil': 'Brazil',
    'brazilian': 'Brazil',
    'thailand': 'Thailand',
    'thai': 'Thailand',
    'malaysia': 'Malaysia',
    'malaysian': 'Malaysia',
    'singapore': 'Singapore',
    'indonesia': 'Indonesia',
    'indonesian': 'Indonesia',
    'philippines': 'Philippines',
    'australia': 'Australia',
    'australian': 'Australia',
    'spain': 'Spain',
    'spanish': 'Spain',
    'belgium': 'Belgium',
    'belgian': 'Belgium',
    'sweden': 'Sweden',
    'swedish': 'Sweden',
    'russia': 'Russia',
    'russian': 'Russia',
    'iran': 'Iran',
    'iranian': 'Iran',
    'saudi arabia': 'Saudi Arabia',
    'saudi': 'Saudi Arabia',
    'venezuela': 'Venezuela',
    'venezuelan': 'Venezuela',
    'colombia': 'Colombia',
    'colombian': 'Colombia',
    'chile': 'Chile',
    'chilean': 'Chile',
    'argentina': 'Argentina',
    'argentine': 'Argentina',
    'european union': 'European Union',
    'eu ': 'European Union',
    ' eu.': 'European Union',
    'european': 'European Union',
}

# Words that look like cashtags but aren't tickers (false-positive guard).
CASHTAG_BLOCKLIST: Set[str] = {
    'USA', 'USD', 'EU', 'UK', 'CEO', 'CFO', 'COO', 'GDP', 'CPI',
    'IRS', 'FBI', 'CIA', 'DOJ', 'EPA', 'FED', 'OPEC', 'NATO',
    'TV', 'AM', 'PM', 'OK',
}


def fetch_recent_statuses(
    account_id: str = TRUMP_ACCOUNT_ID,
    limit: int = 40,
    max_id: Optional[str] = None,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """
    GET the public timeline for an account.

    Parameters
    ----------
    account_id
        Mastodon-compatible account id.
    limit
        Number of statuses to request (API default 20, max 40).
    max_id
        For pagination; return statuses older than this id.
    timeout
        HTTP timeout in seconds.

    Returns
    -------
    Raw list of status dicts. Empty list on HTTP error.
    """
    url = TRUTH_SOCIAL_API.format(account_id=account_id)
    params: Dict[str, Any] = {'limit': limit}
    if max_id:
        params['max_id'] = max_id
    try:
        resp = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            logger.warning('Unexpected Truth Social response shape: %s', type(data))
            return []
        return data
    except requests.exceptions.RequestException as exc:
        logger.warning('Truth Social fetch failed: %s', exc)
        return []
    except ValueError as exc:
        logger.warning('Truth Social JSON decode failed: %s', exc)
        return []


def strip_html(html: str) -> str:
    """Strip HTML tags + emoji shortcodes, return plain text."""
    if not html:
        return ''
    # Pre-process: replace <br> variants with explicit space markers so the
    # parser can't drop them. BS4 sometimes silently drops self-closing tags
    # depending on the surrounding markup.
    pre = re.sub(r'<br\s*/?>', ' \n ', html, flags=re.IGNORECASE)
    soup = BeautifulSoup(pre, 'html.parser')
    text = soup.get_text(separator=' ')
    # Collapse repeated whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def parse_iso(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp into an aware UTC datetime."""
    # Mastodon usually emits 2024-01-15T18:30:00.000Z
    if ts.endswith('Z'):
        ts = ts[:-1] + '+00:00'
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# ── NER ───────────────────────────────────────────────────────────────────

def extract_tickers(text: str, alias_dict: Optional[Dict[str, str]] = None) -> List[str]:
    """
    Extract tickers from post text.

    Combines:
    1. Cashtag regex ($TICKER) — high precision
    2. Company-name alias dictionary lookup — needs case-insensitive match,
       prefers longer aliases (so "u.s. steel" wins over "us")

    Returns deduplicated list of tickers in encounter order.
    """
    if not text:
        return []

    aliases = dict(FALLBACK_TICKER_ALIASES)
    if alias_dict:
        aliases.update(alias_dict)

    found: List[str] = []
    seen: Set[str] = set()

    # 1. Cashtags
    for m in CASHTAG_RE.finditer(text):
        sym = m.group(1)
        if sym in CASHTAG_BLOCKLIST:
            continue
        # Require at least one letter OR an exchange suffix — pure digits
        # like "$100" are dollar amounts, not tickers.
        has_letter = any(c.isalpha() for c in sym)
        has_suffix = '.' in sym
        if not (has_letter or has_suffix):
            continue
        if sym not in seen:
            seen.add(sym)
            found.append(sym)

    # 2. Alias dict — match longest aliases first to avoid "us" stealing
    # "u.s. steel". Use word boundaries so "intel" doesn't match "intelligence".
    text_lower = text.lower()
    sorted_aliases = sorted(aliases.keys(), key=len, reverse=True)
    consumed_spans: List[tuple] = []  # (start, end) ranges already matched

    def _overlaps(start: int, end: int) -> bool:
        for s, e in consumed_spans:
            if start < e and end > s:
                return True
        return False

    for alias in sorted_aliases:
        # Match as whole word/phrase. We allow alias to span non-word chars
        # within itself (e.g. "u.s. steel"), but require word boundaries on
        # the outside.
        pattern = r'(?<![A-Za-z0-9])' + re.escape(alias) + r'(?![A-Za-z0-9])'
        for m in re.finditer(pattern, text_lower):
            if _overlaps(m.start(), m.end()):
                continue
            consumed_spans.append((m.start(), m.end()))
            ticker = aliases[alias]
            if ticker not in seen:
                seen.add(ticker)
                found.append(ticker)

    return found


def extract_sectors(text: str) -> List[str]:
    """Extract sector keywords from post text. Returns deduplicated list."""
    if not text:
        return []
    text_lower = ' ' + text.lower() + ' '  # padding for ' ai ' style keys
    seen: Set[str] = set()
    found: List[str] = []
    for keyword, canonical in SECTOR_KEYWORDS.items():
        if keyword in text_lower and canonical not in seen:
            seen.add(canonical)
            found.append(canonical)
    return found


def extract_countries(text: str) -> List[str]:
    """Extract country / nationality mentions. Returns deduplicated list."""
    if not text:
        return []
    text_lower = ' ' + text.lower() + ' '
    seen: Set[str] = set()
    found: List[str] = []
    # Sort by length desc so "south korea" wins over "korea"
    for keyword in sorted(COUNTRY_KEYWORDS.keys(), key=len, reverse=True):
        if keyword in text_lower:
            canonical = COUNTRY_KEYWORDS[keyword]
            if canonical not in seen:
                seen.add(canonical)
                found.append(canonical)
    return found


def parse_status(
    status: Dict[str, Any],
    alias_dict: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Convert a raw API status dict into our DB row shape.

    Returns None if the status is unparseable (missing id / created_at).
    """
    post_id = status.get('id')
    created_at = status.get('created_at')
    content = status.get('content', '') or ''
    if not post_id or not created_at:
        return None

    text = strip_html(content)
    if not text:
        # Image-only post — skip per spec ("Don't include images. Just text.")
        return None

    try:
        posted_at = parse_iso(created_at)
    except (ValueError, TypeError) as exc:
        logger.debug('Bad timestamp %s: %s', created_at, exc)
        return None

    return {
        'post_id': str(post_id),
        'posted_at': posted_at.isoformat(),
        'text': text,
        'extracted_tickers': extract_tickers(text, alias_dict),
        'extracted_sectors': extract_sectors(text),
        'extracted_countries': extract_countries(text),
        'sentiment': None,  # v1: leave as null; sentiment model out of scope
    }


def fetch_and_parse(
    alias_dict: Optional[Dict[str, str]] = None,
    limit: int = 40,
) -> List[Dict[str, Any]]:
    """
    One-shot fetcher: pull the latest N statuses, parse, return DB rows.

    Skips media-only posts and rows that fail validation.
    """
    raw = fetch_recent_statuses(limit=limit)
    rows: List[Dict[str, Any]] = []
    for status in raw:
        parsed = parse_status(status, alias_dict)
        if parsed is not None:
            rows.append(parsed)
    return rows
