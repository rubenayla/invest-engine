"""
Activist Stakes Database — schema, storage, and signal computation.

Stores SC 13D/13G filings (5%+ ownership stakes) and computes
aggregate activist/passive signals.
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
    """Create activist tables if they don't exist."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS activist_stakes (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            cik TEXT NOT NULL,
            accession_number TEXT NOT NULL,
            filing_date TEXT NOT NULL,
            holder_name TEXT NOT NULL,
            form_type TEXT NOT NULL,
            shares_held REAL,
            percent_of_class REAL,
            purpose_text TEXT,
            is_activist INTEGER DEFAULT 0,
            UNIQUE(accession_number, holder_name)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_activist_ticker
            ON activist_stakes(ticker)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_activist_ticker_date
            ON activist_stakes(ticker, filing_date)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS activist_fetch_log (
            ticker TEXT PRIMARY KEY,
            cik TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            filing_count INTEGER DEFAULT 0,
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
                INSERT INTO activist_stakes
                (ticker, cik, accession_number, filing_date, holder_name,
                 form_type, shares_held, percent_of_class, purpose_text, is_activist)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                s["ticker"], s["cik"], s["accession_number"],
                s["filing_date"], s["holder_name"], s["form_type"],
                s.get("shares_held"), s.get("percent_of_class"),
                s.get("purpose_text", ""), s.get("is_activist", 0),
            ))
            inserted += cur.rowcount
        except Exception:
            conn.rollback()
    conn.commit()
    return inserted


def log_fetch(conn, ticker: str, cik: str,
              filing_count: int, status: str = "ok") -> None:
    """Record that we fetched activist data for a ticker."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO activist_fetch_log (ticker, cik, fetched_at, filing_count, status)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (ticker) DO UPDATE SET
            cik = EXCLUDED.cik,
            fetched_at = EXCLUDED.fetched_at,
            filing_count = EXCLUDED.filing_count,
            status = EXCLUDED.status
    """, (ticker, cik, datetime.utcnow().isoformat(), filing_count, status))
    conn.commit()


def get_known_accessions(conn, ticker: str) -> Set[str]:
    """Get set of accession numbers already stored for a ticker."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT accession_number FROM activist_stakes WHERE ticker = %s",
            (ticker,),
        )
        rows = cur.fetchall()
        return {r[0] for r in rows}
    except Exception:
        conn.rollback()
        return set()


def compute_activist_signal(conn, ticker: str,
                            lookback_days: int = 365) -> Dict[str, Any]:
    """
    Compute aggregate activist/passive signal for a ticker.

    Returns dict with: has_data, activist_count, passive_count,
    max_stake_pct, recent_activist_name, total_holders_5pct.
    """
    no_data = {
        "has_data": False,
        "activist_count": 0,
        "passive_count": 0,
        "max_stake_pct": None,
        "recent_activist_name": None,
        "total_holders_5pct": 0,
    }

    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM activist_stakes LIMIT 1")
    except Exception:
        conn.rollback()
        return no_data

    cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    cur = conn.cursor()
    cur.execute("""
        SELECT holder_name, form_type, shares_held, percent_of_class,
               filing_date, is_activist
        FROM activist_stakes
        WHERE ticker = %s AND filing_date >= %s
        ORDER BY filing_date DESC
    """, (ticker, cutoff))
    rows = cur.fetchall()

    if not rows:
        return no_data

    activist_count = 0
    passive_count = 0
    max_stake_pct = None
    recent_activist_name = None
    holders = set()

    for holder_name, form_type, shares_held, pct, filing_date, is_activist in rows:
        holders.add(holder_name)
        if is_activist:
            activist_count += 1
            if recent_activist_name is None:
                recent_activist_name = holder_name
        else:
            passive_count += 1

        if pct is not None:
            if max_stake_pct is None or pct > max_stake_pct:
                max_stake_pct = pct

    return {
        "has_data": True,
        "activist_count": activist_count,
        "passive_count": passive_count,
        "max_stake_pct": round(max_stake_pct, 2) if max_stake_pct is not None else None,
        "recent_activist_name": recent_activist_name,
        "total_holders_5pct": len(holders),
    }
