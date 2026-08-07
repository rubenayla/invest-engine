"""
Polymarket Trump-policy market database — schema, upsert, deltas, alerts.

Stores active Polymarket prediction markets that match Trump-administration
policy themes (tariffs, exec orders, Fed actions, cabinet picks, etc.).

Snapshots prices on every poll so we can compute 24h price-change deltas in
percentage points (pp). Big moves (>10pp/24h) get pushed into a
`policy_alerts` table for the feed.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import psycopg2.extras

logger = logging.getLogger(__name__)

# Alert threshold — any 24h Yes-price move of this size in percentage points
# becomes a policy_alerts row. 10pp is loud but still triggers a few times
# per week during volatile policy windows.
ALERT_PP_THRESHOLD = 10.0

# Markets thinner than this lifetime volume are excluded from alerts so we
# don't surface noise from a single $50 trade swinging the price 30pp.
MIN_VOLUME_FOR_ALERT = 10_000.0


def ensure_schema(conn) -> None:
    """Create trump_policy_markets + history + alerts tables if absent."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trump_policy_markets (
            market_id TEXT PRIMARY KEY,
            question TEXT NOT NULL,
            category TEXT NOT NULL,
            current_yes_price REAL,
            current_no_price REAL,
            previous_yes_price REAL,
            yes_price_24h_ago REAL,
            volume_24h REAL DEFAULT 0,
            volume_total REAL DEFAULT 0,
            liquidity REAL DEFAULT 0,
            close_date TIMESTAMPTZ,
            slug TEXT,
            url TEXT,
            tags TEXT[],
            metadata JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            last_updated TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trump_policy_category
            ON trump_policy_markets(category)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trump_policy_volume_24h
            ON trump_policy_markets(volume_24h DESC)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trump_policy_close_date
            ON trump_policy_markets(close_date)
    """)

    # Price history — append-only, used to compute 24h deltas.
    # We snapshot on every poll so even sparse polls get usable deltas.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS trump_policy_price_history (
            id SERIAL PRIMARY KEY,
            market_id TEXT NOT NULL,
            yes_price REAL,
            no_price REAL,
            volume_total REAL,
            recorded_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_trump_policy_history_market_time
            ON trump_policy_price_history(market_id, recorded_at DESC)
    """)

    # Alerts table — populated when |Δ24h| >= ALERT_PP_THRESHOLD.
    # `acknowledged` lets the dashboard mark alerts as seen without deleting.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS policy_alerts (
            id SERIAL PRIMARY KEY,
            market_id TEXT NOT NULL,
            question TEXT NOT NULL,
            category TEXT NOT NULL,
            yes_price REAL,
            previous_yes_price REAL,
            delta_pp REAL NOT NULL,
            volume_24h REAL,
            url TEXT,
            triggered_at TIMESTAMPTZ DEFAULT NOW(),
            acknowledged BOOLEAN DEFAULT FALSE,
            UNIQUE(market_id, triggered_at)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_policy_alerts_triggered
            ON policy_alerts(triggered_at DESC)
    """)
    conn.commit()


def get_yes_price_24h_ago(conn, market_id: str) -> float | None:
    """Return the most recent yes_price snapshot from ~24h ago.

    Looks for snapshots in the [12h, 36h] window — a poll that ran 18h or
    30h ago is still close enough to "24h" for alerting purposes. We don't
    interpolate; we just take the closest snapshot inside the window.
    """
    cur = conn.cursor()
    now = datetime.now(timezone.utc)
    lower = now - timedelta(hours=36)
    upper = now - timedelta(hours=12)
    cur.execute("""
        SELECT yes_price, recorded_at
        FROM trump_policy_price_history
        WHERE market_id = %s
          AND recorded_at BETWEEN %s AND %s
          AND yes_price IS NOT NULL
        ORDER BY ABS(EXTRACT(EPOCH FROM (recorded_at - (NOW() - INTERVAL '24 hours'))))
        LIMIT 1
    """, (market_id, lower, upper))
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


def upsert_market(conn, market: Dict[str, Any]) -> Dict[str, Any]:
    """Insert or update a single market row.

    Returns dict with `previous_yes_price` (the value that was in the row
    before this update) and `yes_price_24h_ago` (snapshot near 24h ago) so
    the caller can compute deltas.
    """
    cur = conn.cursor()
    market_id = market['market_id']

    # Capture previous values BEFORE upsert so we can return them
    cur.execute("""
        SELECT current_yes_price FROM trump_policy_markets WHERE market_id = %s
    """, (market_id,))
    prev_row = cur.fetchone()
    previous_yes_price = float(prev_row[0]) if prev_row and prev_row[0] is not None else None

    yes_price_24h_ago = get_yes_price_24h_ago(conn, market_id)

    metadata_json = json.dumps(market.get('raw') or {})
    tags = market.get('tags') or []

    cur.execute("""
        INSERT INTO trump_policy_markets (
            market_id, question, category,
            current_yes_price, current_no_price,
            previous_yes_price, yes_price_24h_ago,
            volume_24h, volume_total, liquidity,
            close_date, slug, url, tags, metadata,
            last_updated
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
        ON CONFLICT (market_id) DO UPDATE SET
            question = EXCLUDED.question,
            category = EXCLUDED.category,
            previous_yes_price = trump_policy_markets.current_yes_price,
            current_yes_price = EXCLUDED.current_yes_price,
            current_no_price = EXCLUDED.current_no_price,
            yes_price_24h_ago = EXCLUDED.yes_price_24h_ago,
            volume_24h = EXCLUDED.volume_24h,
            volume_total = EXCLUDED.volume_total,
            liquidity = EXCLUDED.liquidity,
            close_date = EXCLUDED.close_date,
            slug = EXCLUDED.slug,
            url = EXCLUDED.url,
            tags = EXCLUDED.tags,
            metadata = EXCLUDED.metadata,
            last_updated = NOW()
    """, (
        market_id, market.get('question', ''), market.get('category', 'other'),
        market.get('yes_price'), market.get('no_price'),
        previous_yes_price, yes_price_24h_ago,
        market.get('volume_24h', 0), market.get('volume_total', 0),
        market.get('liquidity', 0),
        market.get('close_date'),
        market.get('slug'), market.get('url'),
        tags, metadata_json,
    ))

    # Append to price history
    cur.execute("""
        INSERT INTO trump_policy_price_history
            (market_id, yes_price, no_price, volume_total)
        VALUES (%s, %s, %s, %s)
    """, (
        market_id, market.get('yes_price'), market.get('no_price'),
        market.get('volume_total', 0),
    ))
    conn.commit()
    return {
        'previous_yes_price': previous_yes_price,
        'yes_price_24h_ago': yes_price_24h_ago,
    }


def upsert_markets(conn, markets: List[Dict[str, Any]]) -> int:
    """Bulk upsert. Returns count processed."""
    count = 0
    for m in markets:
        try:
            upsert_market(conn, m)
            count += 1
        except Exception as exc:
            logger.warning('Failed upsert for market %s: %s', m.get('market_id'), exc)
            conn.rollback()
    return count


def compute_and_record_alerts(conn, markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """For each market, check its 24h-ago snapshot vs current and emit alerts.

    Returns a list of alert dicts that were inserted (deduped via the
    UNIQUE(market_id, triggered_at) constraint — within a single run we
    only emit at most one alert per market).
    """
    alerts: list[dict] = []
    cur = conn.cursor()
    for m in markets:
        yes_now = m.get('yes_price')
        if yes_now is None:
            continue
        if (m.get('volume_total') or 0) < MIN_VOLUME_FOR_ALERT:
            continue

        yes_24h = get_yes_price_24h_ago(conn, m['market_id'])
        if yes_24h is None:
            continue

        delta_pp = (yes_now - yes_24h) * 100.0  # both prices are 0-1, delta in pp
        if abs(delta_pp) < ALERT_PP_THRESHOLD:
            continue

        try:
            cur.execute("""
                INSERT INTO policy_alerts (
                    market_id, question, category,
                    yes_price, previous_yes_price, delta_pp,
                    volume_24h, url
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (market_id, triggered_at) DO NOTHING
                RETURNING id
            """, (
                m['market_id'], m.get('question', ''), m.get('category', 'other'),
                yes_now, yes_24h, delta_pp,
                m.get('volume_24h', 0), m.get('url', ''),
            ))
            row = cur.fetchone()
            if row:
                alerts.append({
                    'id': row[0],
                    'market_id': m['market_id'],
                    'question': m['question'],
                    'category': m.get('category'),
                    'delta_pp': delta_pp,
                    'yes_price': yes_now,
                })
        except Exception as exc:
            logger.warning('Failed alert insert for %s: %s', m.get('market_id'), exc)
            conn.rollback()
    conn.commit()
    return alerts


def delete_stale_markets(conn, kept_market_ids: List[str]) -> int:
    """Remove markets no longer in the latest fetch.

    Markets disappear from the gamma-api active list when they resolve, get
    delisted, or no longer match our keyword filter. Drop them so the feed
    only shows live policy bets.

    Returns count deleted. Empty kept-list is a no-op safeguard against
    accidentally wiping the table when the fetch fails.
    """
    if not kept_market_ids:
        return 0
    cur = conn.cursor()
    cur.execute("""
        DELETE FROM trump_policy_markets
        WHERE market_id != ALL(%s)
    """, (kept_market_ids,))
    deleted = cur.rowcount
    conn.commit()
    return deleted


def get_active_markets(
    conn,
    *,
    limit: int = 50,
    min_volume_total: float = 0,
    sort_by_24h_move: bool = True,
) -> List[Dict[str, Any]]:
    """Return current snapshot of tracked markets, ready to render.

    Computes display-ready 24h delta in pp and color-codes via the
    `delta_class` field ('pos' / 'neg' / '').
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT market_id, question, category,
                   current_yes_price, current_no_price,
                   previous_yes_price, yes_price_24h_ago,
                   volume_24h, volume_total, liquidity,
                   close_date, url, tags, last_updated
            FROM trump_policy_markets
            WHERE close_date IS NULL OR close_date > NOW()
              AND volume_total >= %s
            ORDER BY volume_24h DESC
            LIMIT %s
        """, (min_volume_total, limit * 3))  # over-fetch to allow re-sort
    except Exception:
        conn.rollback()
        return []

    rows = cur.fetchall()
    out: list[dict] = []
    for r in rows:
        d = dict(r)
        yes = d.get('current_yes_price')
        yes_24h = d.get('yes_price_24h_ago')
        if yes is not None and yes_24h is not None:
            delta_pp = (yes - yes_24h) * 100.0
        else:
            delta_pp = None
        d['delta_pp'] = delta_pp
        if delta_pp is None:
            d['delta_class'] = ''
        elif delta_pp > 0:
            d['delta_class'] = 'pos'
        elif delta_pp < 0:
            d['delta_class'] = 'neg'
        else:
            d['delta_class'] = ''
        out.append(d)

    if sort_by_24h_move:
        out.sort(key=lambda x: abs(x['delta_pp']) if x['delta_pp'] is not None else -1,
                 reverse=True)
    return out[:limit]


def get_recent_alerts(conn, *, hours: int = 48, limit: int = 20) -> List[Dict[str, Any]]:
    """Return recent unacknowledged policy alerts."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        cur.execute("""
            SELECT id, market_id, question, category,
                   yes_price, previous_yes_price, delta_pp,
                   volume_24h, url, triggered_at, acknowledged
            FROM policy_alerts
            WHERE triggered_at >= %s
            ORDER BY ABS(delta_pp) DESC, triggered_at DESC
            LIMIT %s
        """, (cutoff, limit))
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        conn.rollback()
        return []
