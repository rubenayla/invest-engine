"""
Japan Large Shareholding Database — schema, storage, and signal computation.

Stores EDINET 大量保有報告書 (large shareholding reports) for Japanese equities
and computes aggregate signals.
"""

import logging
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "stock_data.db"


def ensure_schema(conn) -> None:
    """Create Japan large shareholding tables if they don't exist."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS japan_large_stakes (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            edinet_code TEXT,
            doc_id TEXT NOT NULL,
            report_date TEXT NOT NULL,
            holder_name TEXT NOT NULL,
            shares_held REAL,
            percent_of_class REAL,
            purpose TEXT,
            report_type TEXT,
            UNIQUE(doc_id, holder_name)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_japan_stakes_ticker
            ON japan_large_stakes(ticker)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_japan_stakes_ticker_date
            ON japan_large_stakes(ticker, report_date)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS edinet_fetch_log (
            ticker TEXT PRIMARY KEY,
            edinet_code TEXT,
            fetched_at TEXT NOT NULL,
            doc_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ok'
        )
    """)
    conn.commit()


def insert_stakes(conn, stakes: List[Dict[str, Any]]) -> int:
    """Insert stakes, ignoring duplicates. Returns count inserted."""
    inserted = 0
    cur = conn.cursor()
    for s in stakes:
        try:
            cur.execute("""
                INSERT INTO japan_large_stakes
                (ticker, edinet_code, doc_id, report_date, holder_name,
                 shares_held, percent_of_class, purpose, report_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                s["ticker"], s.get("edinet_code", ""), s["doc_id"],
                s["report_date"], s["holder_name"],
                s.get("shares_held"), s.get("percent_of_class"),
                s.get("purpose", ""), s.get("report_type", ""),
            ))
            inserted += cur.rowcount
        except Exception:
            conn.rollback()
    conn.commit()
    return inserted


def log_fetch(conn, ticker: str, edinet_code: str,
              doc_count: int, status: str = "ok") -> None:
    """Record that we fetched EDINET data for a ticker."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO edinet_fetch_log
        (ticker, edinet_code, fetched_at, doc_count, status)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (ticker) DO UPDATE SET
            edinet_code = EXCLUDED.edinet_code,
            fetched_at = EXCLUDED.fetched_at,
            doc_count = EXCLUDED.doc_count,
            status = EXCLUDED.status
    """, (ticker, edinet_code, datetime.utcnow().isoformat(), doc_count, status))
    conn.commit()


def get_known_doc_ids(conn, ticker: str) -> Set[str]:
    """Get set of doc IDs already stored for a ticker."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT doc_id FROM japan_large_stakes WHERE ticker = %s",
            (ticker,),
        )
        rows = cur.fetchall()
        return {r[0] for r in rows}
    except Exception:
        conn.rollback()
        return set()


def compute_japan_signal(conn, ticker: str,
                         lookback_days: int = 365) -> Dict[str, Any]:
    """
    Compute aggregate Japan large shareholding signal.

    Returns dict with: has_data, holder_count, max_stake_pct,
    recent_holder_name, total_reports.
    """
    no_data = {
        "has_data": False,
        "holder_count": 0,
        "max_stake_pct": None,
        "recent_holder_name": None,
        "total_reports": 0,
    }

    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM japan_large_stakes LIMIT 1")
    except Exception:
        conn.rollback()
        return no_data

    cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    cur = conn.cursor()
    cur.execute("""
        SELECT holder_name, shares_held, percent_of_class, report_date, report_type
        FROM japan_large_stakes
        WHERE ticker = %s AND report_date >= %s
        ORDER BY report_date DESC
    """, (ticker, cutoff))
    rows = cur.fetchall()

    if not rows:
        return no_data

    holders = set()
    max_pct = None
    recent_holder = None

    for holder_name, shares, pct, date, rtype in rows:
        holders.add(holder_name)
        if recent_holder is None:
            recent_holder = holder_name
        if pct is not None:
            if max_pct is None or pct > max_pct:
                max_pct = pct

    return {
        "has_data": True,
        "holder_count": len(holders),
        "max_stake_pct": round(max_pct, 2) if max_pct is not None else None,
        "recent_holder_name": recent_holder,
        "total_reports": len(rows),
    }
