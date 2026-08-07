"""
Truth Social posts database — schema, storage, and signal computation.

Stores Donald Trump's Truth Social posts (Mastodon-compatible API at
truthsocial.com) along with NER-extracted tickers, sectors, and country
tariff targets. Surfaces a "Trump signal" card on /feed for each recent
post containing tradable signal (linked tickers, mentioned sectors, or
tariff-target countries).

Real-time leading indicator (vs the politician_trades PTRs which lag up
to 45 days).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import psycopg2.extensions
import psycopg2.extras

logger = logging.getLogger(__name__)


def ensure_schema(conn) -> None:
    """Create truth_social_posts table if it doesn't exist.

    Idempotent — safe to call on every fetcher run.
    """
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS truth_social_posts (
            post_id TEXT PRIMARY KEY,
            posted_at TIMESTAMPTZ NOT NULL,
            text TEXT NOT NULL,
            extracted_tickers TEXT[] NOT NULL DEFAULT '{}',
            extracted_sectors TEXT[] NOT NULL DEFAULT '{}',
            extracted_countries TEXT[] NOT NULL DEFAULT '{}',
            sentiment REAL,
            fetched_at TIMESTAMPTZ NOT NULL
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_truth_social_posted_at
            ON truth_social_posts(posted_at DESC)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_truth_social_tickers
            ON truth_social_posts USING GIN(extracted_tickers)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_truth_social_sectors
            ON truth_social_posts USING GIN(extracted_sectors)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_truth_social_countries
            ON truth_social_posts USING GIN(extracted_countries)
    """)
    conn.commit()


def upsert_posts(conn, posts: List[Dict[str, Any]]) -> int:
    """Insert / update Truth Social posts. Returns count written.

    Uses ON CONFLICT (post_id) DO UPDATE so re-runs refresh extracted
    entities and fetched_at without duplicating rows.
    """
    if not posts:
        return 0

    written = 0
    cur = conn.cursor()
    fetched_at = datetime.now(timezone.utc).isoformat()
    for idx, p in enumerate(posts):
        sp = f'sp_ts_{idx}'
        cur.execute(f'SAVEPOINT {sp}')
        try:
            cur.execute("""
                INSERT INTO truth_social_posts
                (post_id, posted_at, text, extracted_tickers, extracted_sectors,
                 extracted_countries, sentiment, fetched_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO UPDATE SET
                    text = EXCLUDED.text,
                    extracted_tickers = EXCLUDED.extracted_tickers,
                    extracted_sectors = EXCLUDED.extracted_sectors,
                    extracted_countries = EXCLUDED.extracted_countries,
                    sentiment = EXCLUDED.sentiment,
                    fetched_at = EXCLUDED.fetched_at
            """, (
                p['post_id'],
                p['posted_at'],
                p['text'],
                p.get('extracted_tickers', []),
                p.get('extracted_sectors', []),
                p.get('extracted_countries', []),
                p.get('sentiment'),
                fetched_at,
            ))
            written += 1
            cur.execute(f'RELEASE SAVEPOINT {sp}')
        except Exception as exc:
            logger.debug('upsert_posts row failed (%s): %s', p.get('post_id'), exc)
            cur.execute(f'ROLLBACK TO SAVEPOINT {sp}')
    conn.commit()
    return written


def get_known_post_ids(conn, lookback_days: int = 7) -> set:
    """Return set of post_ids already stored within lookback window.

    Used to skip re-extracting NER on unchanged posts (cheap optimisation).
    """
    try:
        cur = conn.cursor()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        cur.execute(
            'SELECT post_id FROM truth_social_posts WHERE posted_at >= %s',
            (cutoff,),
        )
        return {row[0] for row in cur.fetchall()}
    except Exception:
        conn.rollback()
        return set()


def get_recent_posts(
    conn,
    lookback_hours: int = 48,
    limit: int = 20,
    require_signal: bool = True,
) -> List[Dict[str, Any]]:
    """
    Fetch recent Truth Social posts for /feed surfacing.

    Parameters
    ----------
    lookback_hours
        Only return posts newer than this.
    limit
        Maximum cards to return.
    require_signal
        If True, skip posts with no extracted tickers / sectors / countries.

    Returns
    -------
    list of dict with keys: post_id, posted_at, text, extracted_tickers,
    extracted_sectors, extracted_countries, sentiment.
    """
    no_data: List[Dict[str, Any]] = []
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute('SELECT 1 FROM truth_social_posts LIMIT 1')
    except Exception:
        conn.rollback()
        return no_data

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_hours)).isoformat()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if require_signal:
        cur.execute("""
            SELECT post_id, posted_at, text, extracted_tickers,
                   extracted_sectors, extracted_countries, sentiment
            FROM truth_social_posts
            WHERE posted_at >= %s
              AND (cardinality(extracted_tickers) > 0
                   OR cardinality(extracted_sectors) > 0
                   OR cardinality(extracted_countries) > 0)
            ORDER BY posted_at DESC
            LIMIT %s
        """, (cutoff, limit))
    else:
        cur.execute("""
            SELECT post_id, posted_at, text, extracted_tickers,
                   extracted_sectors, extracted_countries, sentiment
            FROM truth_social_posts
            WHERE posted_at >= %s
            ORDER BY posted_at DESC
            LIMIT %s
        """, (cutoff, limit))

    results = []
    for row in cur.fetchall():
        d = dict(row)
        # Ensure isoformat string for JSON serialisation downstream
        pa = d.get('posted_at')
        if isinstance(pa, datetime):
            d['posted_at'] = pa.isoformat()
        results.append(d)
    return results


def get_universe_company_names(conn) -> Dict[str, str]:
    """
    Return {lowercased_company_name: ticker} for known stocks.

    Used to build the NER alias dictionary at fetcher startup. Falls back
    to {} on DB error so the fetcher can still run with the hand-rolled
    fallback dictionary.
    """
    aliases: Dict[str, str] = {}
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT ticker, long_name, short_name
            FROM current_stock_data
            WHERE long_name IS NOT NULL OR short_name IS NOT NULL
        """)
        for ticker, long_name, short_name in cur.fetchall():
            for raw in (long_name, short_name):
                if not raw:
                    continue
                # Strip common corporate suffixes for cleaner matching
                cleaned = _strip_corporate_suffix(raw).strip().lower()
                # Skip dangerous single-word aliases that collide with
                # common English / given names (e.g. "BILL" -> Bill.com
                # would match "Bill Cassidy"). Require at least one space
                # OR length >= 6 OR explicit hand-curated entry in the
                # fallback dict.
                if len(cleaned) < 4:
                    continue
                if ' ' not in cleaned and len(cleaned) < 6:
                    continue
                if cleaned in _COMMON_NAME_BLOCKLIST:
                    continue
                if cleaned not in aliases:
                    aliases[cleaned] = ticker
    except Exception as exc:
        logger.debug('get_universe_company_names failed: %s', exc)
        try:
            conn.rollback()
        except Exception:
            pass
    return aliases


_COMMON_NAME_BLOCKLIST = {
    # Stock long_names that collide with first names, common words, or
    # gibberish that produces noisy matches.
    'bill', 'apple', 'block', 'global', 'general', 'public', 'first',
    'vista', 'home', 'open', 'crown', 'union', 'national', 'standard',
    'industries', 'partners', 'capital', 'energy', 'health', 'tech',
    'technology', 'systems', 'services', 'solutions', 'media', 'group',
    'global industries', 'international', 'world', 'american', 'american airlines',
    'china', 'japan',
}


def _strip_corporate_suffix(name: str) -> str:
    """Remove common corporate suffixes (Inc., Corp., Ltd.) for matching."""
    suffixes = [
        ', Inc.', ' Inc.', ' Inc',
        ', Corp.', ' Corp.', ' Corp', ' Corporation',
        ', Ltd.', ' Ltd.', ' Ltd', ' Limited',
        ' plc', ' PLC', ' LLC', ' L.P.',
        ' Co.', ' Co', ' Company',
        ', S.A.', ' S.A.', ' SA',
        ' AG', ' SE', ' N.V.', ' NV',
        ' Holdings', ' Group',
    ]
    cleaned = name
    for suf in suffixes:
        if cleaned.endswith(suf):
            cleaned = cleaned[:-len(suf)]
    return cleaned


def compute_truth_social_signal(
    conn,
    ticker: str,
    lookback_days: int = 7,
) -> Dict[str, Any]:
    """
    Compute Truth Social signal for a single ticker.

    Returns dict with: has_data, mention_count, recent_posts (list of
    {posted_at, text_snippet}), recency_hours.
    """
    no_data: Dict[str, Any] = {
        'has_data': False,
        'mention_count': 0,
        'recent_posts': [],
        'recency_hours': None,
    }

    try:
        cur = conn.cursor()
        cur.execute('SELECT 1 FROM truth_social_posts LIMIT 1')
    except Exception:
        conn.rollback()
        return no_data

    cutoff = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
    cur = conn.cursor()
    cur.execute("""
        SELECT post_id, posted_at, text
        FROM truth_social_posts
        WHERE %s = ANY(extracted_tickers)
          AND posted_at >= %s
        ORDER BY posted_at DESC
        LIMIT 5
    """, (ticker, cutoff))
    rows = cur.fetchall()

    if not rows:
        return no_data

    recent_posts = []
    last_dt: Optional[datetime] = None
    for post_id, posted_at, text in rows:
        snippet = text[:200] + ('...' if len(text) > 200 else '')
        recent_posts.append({
            'post_id': post_id,
            'posted_at': posted_at.isoformat() if isinstance(posted_at, datetime) else posted_at,
            'snippet': snippet,
        })
        if last_dt is None and isinstance(posted_at, datetime):
            last_dt = posted_at

    recency_hours = None
    if last_dt is not None:
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        recency_hours = int((datetime.now(timezone.utc) - last_dt).total_seconds() / 3600)

    return {
        'has_data': True,
        'mention_count': len(rows),
        'recent_posts': recent_posts,
        'recency_hours': recency_hours,
    }
