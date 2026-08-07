#!/usr/bin/env python3
"""
Polymarket prediction market lookup.

Fetches prediction market probabilities from Polymarket's public API.
Useful for anchoring scenario probabilities in thesis evaluation.

Usage:
    uv run python scripts/polymarket_lookup.py "tariff"
    uv run python scripts/polymarket_lookup.py "fed rate" --min-liquidity 50000
    uv run python scripts/polymarket_lookup.py "bitcoin" --limit 20
    uv run python scripts/polymarket_lookup.py --trump-policy
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GAMMA_API = "https://gamma-api.polymarket.com"
POLYMARKET_URL = "https://polymarket.com/event"
_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "invest-polymarket-lookup/1.0",
}


def _fetch_json(url: str) -> list | dict:
    """Fetch JSON from a URL, returning empty list on error."""
    req = Request(url, headers=_HEADERS)
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception:
        return []


def search_markets(
    query: str,
    *,
    limit: int = 10,
    min_liquidity: float = 0,
    active_only: bool = True,
) -> list[dict]:
    """Search Polymarket for markets matching a query string.

    Uses the gamma API to fetch active markets, then filters client-side
    by keyword since the API lacks native text search.
    """
    base_params: dict = {
        "limit": 100,
        "order": "volume",
        "ascending": "false",
        "active": str(active_only).lower(),
        "closed": "false",
    }
    if min_liquidity > 0:
        base_params["liquidity_num_min"] = str(int(min_liquidity))

    # Fetch multiple pages of markets (API caps at ~100 per page)
    all_markets: list[dict] = []
    max_pages = 5
    for page in range(max_pages):
        params = {**base_params, "offset": str(page * 100)}
        url = f"{GAMMA_API}/markets?{urlencode(params)}"
        batch = _fetch_json(url)
        if not isinstance(batch, list) or not batch:
            break
        all_markets.extend(batch)

    # Also search events (groups of related markets, better coverage)
    events_url = f"{GAMMA_API}/events?limit=50&active=true&closed=false&order=volume&ascending=false"
    events = _fetch_json(events_url)
    if isinstance(events, list):
        for event in events:
            for market in event.get("markets", []):
                if market.get("active") and not market.get("closed"):
                    all_markets.append(market)

    # Client-side keyword filter (case-insensitive)
    keywords = query.lower().split()
    results = []
    seen_questions: set[str] = set()
    for market in all_markets:
        question = (market.get("question") or "").lower()
        description = (market.get("description") or "").lower()
        text = f"{question} {description}"
        if all(kw in text for kw in keywords) and question not in seen_questions:
            seen_questions.add(question)
            results.append(_format_market(market))

    # Sort by volume descending
    results.sort(key=lambda m: m["volume_usd"], reverse=True)
    return results[:limit]


def _format_market(raw: dict) -> dict:
    """Extract the useful fields from a raw market object."""
    outcomes = raw.get("outcomes") or ["Yes", "No"]
    prices_raw = raw.get("outcomePrices") or []

    # Both outcomes and outcomePrices may arrive as JSON strings
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except (json.JSONDecodeError, TypeError):
            outcomes = ["Yes", "No"]

    if isinstance(prices_raw, str):
        try:
            prices_raw = json.loads(prices_raw)
        except (json.JSONDecodeError, TypeError):
            prices_raw = []

    prices = []
    for p in prices_raw:
        try:
            prices.append(float(p))
        except (ValueError, TypeError):
            prices.append(0.0)

    # Build outcome dict
    outcome_probs = {}
    for i, outcome in enumerate(outcomes):
        prob = prices[i] if i < len(prices) else 0.0
        outcome_probs[outcome] = round(prob * 100, 1)

    volume = 0.0
    try:
        volume = float(raw.get("volume") or 0)
    except (ValueError, TypeError):
        pass

    liquidity = 0.0
    try:
        liquidity = float(raw.get("liquidity") or 0)
    except (ValueError, TypeError):
        pass

    slug = raw.get("slug") or ""

    return {
        "question": raw.get("question", ""),
        "probabilities": outcome_probs,
        "volume_usd": round(volume, 2),
        "liquidity_usd": round(liquidity, 2),
        "end_date": raw.get("endDate", ""),
        "url": f"https://polymarket.com/event/{slug}" if slug else "",
    }


# ── Trump-policy filter ──────────────────────────────────────────────────
#
# Categories matter for downstream display + alerting. Each category gets
# (label, list of regexes). Markets are matched against question + description.
# A market may match multiple categories — we pick the first hit, which is
# why the order below is intentional (most-specific to most-generic).
#
# The regexes are intentionally loose: Polymarket question text varies a lot
# ("Trump tariffs on EU 50%?" vs "Will Trump impose tariffs?"), so we want
# recall over precision — the volume threshold + manual review filters out
# the noise.

_TRUMP_TOKEN = re.compile(r'\btrump\b', re.IGNORECASE)
_POLITICAL_NOISE = re.compile(
    r'\b(approval rating|say\b|the villages|gold cards?|visit|tweet|truth social|'
    r'rino|president(?:ial)? run|election day|2028\s+(?:republican|democratic|'
    r'general|presidential)|win the 2028|nomination)\b',
    re.IGNORECASE,
)

POLICY_CATEGORIES: list[tuple[str, list[re.Pattern]]] = [
    ('tariffs', [
        re.compile(r'\btariffs?\b', re.IGNORECASE),
        re.compile(r'\btrade\s+(?:war|deal)\b', re.IGNORECASE),
        re.compile(r'\bimport\s+(?:duty|duties|tax)\b', re.IGNORECASE),
    ]),
    ('fed_actions', [
        re.compile(r'\b(?:federal reserve|fed)\b.*\b(?:rate|cut|hike|hold)\b', re.IGNORECASE),
        re.compile(r'\b(?:rate cut|rate hike|rate hold)\b', re.IGNORECASE),
        re.compile(r'\bpowell\b', re.IGNORECASE),
        re.compile(r'\bfomc\b', re.IGNORECASE),
    ]),
    ('executive_orders', [
        re.compile(r'\bexecutive order\b', re.IGNORECASE),
        re.compile(r'\bsign(?:ed|s)?\b.*\border\b', re.IGNORECASE),
    ]),
    ('cabinet_appointments', [
        re.compile(r'\b(?:cabinet|nominee|nominate|confirm(?:ed|ation)?)\b', re.IGNORECASE),
        re.compile(r'\b(?:secretary of|attorney general|ambassador)\b', re.IGNORECASE),
        re.compile(r'\b(?:fired|resign|step down|replace)\b', re.IGNORECASE),
    ]),
    ('legislation', [
        re.compile(r'\b(?:bill|act|legislation|tax bill|budget|spending)\b', re.IGNORECASE),
        re.compile(r'\b(?:congress|senate|house)\b.*\b(?:pass|approve|vote)\b', re.IGNORECASE),
        re.compile(r'\b(?:debt ceiling|government shutdown|continuing resolution)\b', re.IGNORECASE),
    ]),
    ('china', [
        re.compile(r'\bchina\b', re.IGNORECASE),
        re.compile(r'\bxi jinping\b', re.IGNORECASE),
        re.compile(r'\btaiwan\b', re.IGNORECASE),
    ]),
    ('energy_oil', [
        re.compile(r'\boil\b', re.IGNORECASE),
        re.compile(r'\b(?:opec|wti|brent|crude)\b', re.IGNORECASE),
        re.compile(r'\b(?:energy|gas|drilling|pipeline|keystone)\b', re.IGNORECASE),
    ]),
    ('crypto', [
        re.compile(r'\b(?:crypto|bitcoin|ethereum|stablecoin|sec)\b', re.IGNORECASE),
        re.compile(r'\b(?:strategic reserve|digital asset)\b', re.IGNORECASE),
    ]),
    ('immigration', [
        re.compile(r'\b(?:immigration|border|deport|asylum|migrant|ice|visa)\b', re.IGNORECASE),
    ]),
    ('foreign_policy', [
        re.compile(r'\b(?:russia|russian|ukraine|ukrainian|iran|iranian|israel|israeli|'
                   r'gaza|nato|north korea|hamas|houthi|venezuela)\b', re.IGNORECASE),
    ]),
]


def _classify_policy_category(question: str, description: str) -> str | None:
    """Return the first matching policy category, or None if no match."""
    text = f'{question} {description}'
    for category, patterns in POLICY_CATEGORIES:
        for pat in patterns:
            if pat.search(text):
                return category
    return None


def _is_trump_relevant(question: str, description: str) -> bool:
    """A market is Trump-relevant if it mentions Trump OR is about a tariff/exec
    order / Fed-action policy theme during a Trump administration."""
    text = f'{question} {description}'
    if _TRUMP_TOKEN.search(text):
        return True
    # Tariff / executive-order / Fed / cabinet / trade-deal markets are
    # de-facto Trump-policy in the current administration regardless of
    # explicit name mention.
    standalone_patterns = [
        re.compile(r'\btariffs?\b', re.IGNORECASE),
        re.compile(r'\bexecutive order\b', re.IGNORECASE),
        re.compile(r'\b(?:cabinet pick|nominee confirm)\b', re.IGNORECASE),
        re.compile(r'\btrade\s+(?:deal|war|agreement)\b', re.IGNORECASE),
        re.compile(r'\b(?:fed|fomc|federal reserve)\b.*\b(?:cut|hike|hold|rate|decision)\b',
                   re.IGNORECASE),
        re.compile(r'\b(?:rate cut|rate hike)\b', re.IGNORECASE),
        re.compile(r'\bpowell\b', re.IGNORECASE),
    ]
    return any(p.search(text) for p in standalone_patterns)


def _is_low_signal_political_noise(question: str) -> bool:
    """Filter out approval-rating, social-media, and trivia markets that
    technically mention Trump but aren't policy-relevant."""
    return bool(_POLITICAL_NOISE.search(question))


def classify_trump_policy_market(question: str, description: str = '') -> str | None:
    """Public entry point used by tests and by the policy-fetcher.

    Returns the policy category string if the market is a Trump-relevant
    policy market, else None.
    """
    if not question:
        return None
    if _is_low_signal_political_noise(question):
        return None
    if not _is_trump_relevant(question, description):
        return None
    return _classify_policy_category(question, description)


def _parse_iso_dt(s: str | None) -> datetime | None:
    """Parse an ISO datetime string (with optional Z suffix)."""
    if not s:
        return None
    try:
        # Accept '2026-04-30T19:00:00Z' or '2026-04-30T19:00:00.123456Z'
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None


def fetch_trump_policy_markets(
    *,
    max_pages: int = 6,
    page_size: int = 500,
    min_volume_total: float = 0,
    include_closed: bool = False,
) -> list[dict]:
    """Fetch active Polymarket markets relevant to Trump-administration policy.

    Iterates through gamma-api `/markets` pages, applies the keyword filter,
    and returns a normalized list with category, prices, volumes, and metadata.

    Parameters
    ----------
    max_pages : int
        How many 500-row pages to fetch (Polymarket caps page size).
    page_size : int
        Items per page.
    min_volume_total : float
        Filter out thin markets below this lifetime volume threshold.
    include_closed : bool
        If True, include closed markets (useful for backfill).

    Returns
    -------
    list[dict]
        Each dict has: market_id, question, category, yes_price, no_price,
        volume_24h, volume_total, close_date (datetime or None), tags,
        slug, url, raw (passthrough metadata for jsonb storage).
    """
    base_params: dict = {
        'limit': page_size,
        'order': 'volume',
        'ascending': 'false',
    }
    if not include_closed:
        base_params['closed'] = 'false'
        base_params['active'] = 'true'

    now_utc = datetime.now(timezone.utc)
    results: list[dict] = []
    seen_ids: set[str] = set()

    for page in range(max_pages):
        params = {**base_params, 'offset': str(page * page_size)}
        url = f'{GAMMA_API}/markets?{urlencode(params)}'
        batch = _fetch_json(url)
        if not isinstance(batch, list) or not batch:
            break
        for raw in batch:
            mid = str(raw.get('id') or '')
            if not mid or mid in seen_ids:
                continue
            question = raw.get('question') or ''
            description = raw.get('description') or ''
            category = classify_trump_policy_market(question, description)
            if not category:
                continue

            # Filter: must be active and not yet ended
            if not include_closed:
                if raw.get('closed') or not raw.get('active', True):
                    continue
                end_dt = _parse_iso_dt(raw.get('endDate'))
                if end_dt and end_dt < now_utc:
                    continue

            formatted = _format_market(raw)
            yes_price = formatted['probabilities'].get('Yes')
            no_price = formatted['probabilities'].get('No')

            volume_total = formatted['volume_usd']
            if volume_total < min_volume_total:
                continue

            volume_24h = 0.0
            try:
                volume_24h = float(raw.get('volume24hr') or 0)
            except (ValueError, TypeError):
                pass

            tags: list[str] = []
            for ev in (raw.get('events') or []):
                for t in (ev.get('tags') or []):
                    if isinstance(t, dict):
                        label = t.get('label') or t.get('slug') or ''
                    else:
                        label = str(t)
                    if label:
                        tags.append(label)

            results.append({
                'market_id': mid,
                'question': question,
                'category': category,
                'yes_price': (yes_price / 100.0) if yes_price is not None else None,
                'no_price': (no_price / 100.0) if no_price is not None else None,
                'volume_24h': round(volume_24h, 2),
                'volume_total': volume_total,
                'liquidity': formatted['liquidity_usd'],
                'close_date': _parse_iso_dt(raw.get('endDate')),
                'slug': raw.get('slug') or '',
                'url': formatted['url'],
                'tags': sorted(set(tags)),
                'raw': {
                    'outcomes': formatted.get('probabilities'),
                    'description': (description or '')[:1000],
                    'updatedAt': raw.get('updatedAt'),
                },
            })
            seen_ids.add(mid)

    # Sort by 24h volume so highest-activity markets surface first
    results.sort(key=lambda m: m['volume_24h'], reverse=True)
    return results


def print_results(results: list[dict], query: str) -> None:
    """Pretty-print market results to stdout."""
    if not results:
        print(f"No active markets found for '{query}'")
        return

    print(f"\n{'='*70}")
    print(f"  Polymarket: '{query}' — {len(results)} market(s) found")
    print(f"{'='*70}\n")

    for i, m in enumerate(results, 1):
        print(f"  {i}. {m['question']}")

        # Show probabilities
        probs_str = " | ".join(f"{k}: {v}%" for k, v in m["probabilities"].items())
        print(f"     {probs_str}")

        # Volume and liquidity
        vol = m["volume_usd"]
        liq = m["liquidity_usd"]
        vol_str = f"${vol/1e6:.1f}M" if vol >= 1e6 else f"${vol/1e3:.0f}K" if vol >= 1e3 else f"${vol:.0f}"
        liq_str = f"${liq/1e6:.1f}M" if liq >= 1e6 else f"${liq/1e3:.0f}K" if liq >= 1e3 else f"${liq:.0f}"
        print(f"     Volume: {vol_str}  |  Liquidity: {liq_str}")

        if m["end_date"]:
            print(f"     Resolves: {m['end_date'][:10]}")
        if m["url"]:
            print(f"     {m['url']}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Search Polymarket prediction markets")
    parser.add_argument("query", nargs='?', default=None,
                        help="Keywords to search for (e.g. 'tariff', 'fed rate')")
    parser.add_argument("--limit", type=int, default=10, help="Max results (default: 10)")
    parser.add_argument("--min-liquidity", type=float, default=0, help="Min liquidity in USD")
    parser.add_argument("--min-volume", type=float, default=0,
                        help="Min lifetime volume in USD (trump-policy mode)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--trump-policy", action="store_true",
                        help="Fetch all Trump-administration policy markets (ignores query)")
    args = parser.parse_args()

    if args.trump_policy:
        markets = fetch_trump_policy_markets(min_volume_total=args.min_volume)
        if args.json:
            # Stringify datetimes for JSON
            export = []
            for m in markets[:args.limit] if args.limit else markets:
                row = dict(m)
                cd = row.get('close_date')
                row['close_date'] = cd.isoformat() if cd else None
                export.append(row)
            json.dump(export, sys.stdout, indent=2, default=str)
            print()
            return
        print(f"\n{'='*70}")
        print(f"  Polymarket: Trump-policy markets — {len(markets)} found")
        print(f"{'='*70}\n")
        for i, m in enumerate(markets[:args.limit], 1):
            yes = m['yes_price']
            yes_str = f"{yes*100:.1f}%" if yes is not None else "?"
            v24 = m['volume_24h']
            v24_str = f"${v24/1e3:.1f}K" if v24 >= 1e3 else f"${v24:.0f}"
            close = m['close_date'].strftime('%Y-%m-%d') if m['close_date'] else '?'
            print(f"  {i}. [{m['category']}] {m['question']}")
            print(f"     YES: {yes_str}  |  24h vol: {v24_str}  |  closes: {close}")
            if m['url']:
                print(f"     {m['url']}")
            print()
        return

    if not args.query:
        parser.error('query is required unless --trump-policy is set')
    results = search_markets(args.query, limit=args.limit, min_liquidity=args.min_liquidity)

    if args.json:
        json.dump(results, sys.stdout, indent=2)
        print()
    else:
        print_results(results, args.query)


if __name__ == "__main__":
    main()
