"""
Institutional Holdings Database — schema, storage, and signal computation.

Stores 13F-HR quarterly institutional holdings from "smart money" funds
and computes aggregate holdings signals.
"""

import logging
import psycopg2
import psycopg2.extras
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "stock_data.db"


def ensure_schema(conn) -> None:
    """Create holdings tables if they don't exist."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fund_holdings (
            id SERIAL PRIMARY KEY,
            fund_name TEXT NOT NULL,
            fund_cik TEXT NOT NULL,
            filing_date TEXT NOT NULL,
            quarter TEXT NOT NULL,
            cusip TEXT NOT NULL,
            ticker TEXT,
            issuer_name TEXT,
            shares REAL,
            value_usd REAL,
            UNIQUE(fund_cik, filing_date, cusip)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_holdings_ticker
            ON fund_holdings(ticker)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_holdings_fund_quarter
            ON fund_holdings(fund_cik, quarter)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_holdings_quarter
            ON fund_holdings(quarter)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS holdings_fetch_log (
            fund_cik TEXT PRIMARY KEY,
            fund_name TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            filing_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ok'
        )
    """)
    conn.commit()


def insert_holdings(conn, holdings: List[Dict[str, Any]]) -> int:
    """Insert holdings, ignoring duplicates. Returns count inserted."""
    inserted = 0
    cur = conn.cursor()
    for h in holdings:
        try:
            cur.execute("""
                INSERT INTO fund_holdings
                (fund_name, fund_cik, filing_date, quarter, cusip,
                 ticker, issuer_name, shares, value_usd)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                h["fund_name"], h["fund_cik"], h["filing_date"],
                h["quarter"], h["cusip"], h.get("ticker", ""),
                h.get("issuer_name", ""), h.get("shares"),
                h.get("value_usd"),
            ))
            inserted += cur.rowcount
        except Exception:
            conn.rollback()
    conn.commit()
    return inserted


def log_fetch(conn, fund_cik: str, fund_name: str,
              filing_count: int, status: str = "ok") -> None:
    """Record that we fetched holdings for a fund."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO holdings_fetch_log
        (fund_cik, fund_name, fetched_at, filing_count, status)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (fund_cik) DO UPDATE SET
            fund_name = EXCLUDED.fund_name,
            fetched_at = EXCLUDED.fetched_at,
            filing_count = EXCLUDED.filing_count,
            status = EXCLUDED.status
    """, (fund_cik, fund_name, datetime.utcnow().isoformat(), filing_count, status))
    conn.commit()


def get_known_accessions(conn, fund_cik: str) -> Set[str]:
    """Get set of filing dates already stored for a fund (used as dedup key)."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT filing_date FROM fund_holdings WHERE fund_cik = %s",
            (fund_cik,),
        )
        rows = cur.fetchall()
        return {r[0] for r in rows}
    except Exception:
        conn.rollback()
        return set()


def compute_holdings_signal(conn, ticker: str) -> Dict[str, Any]:
    """
    Compute aggregate institutional holdings signal for a ticker.

    Returns dict with: has_data, smart_money_holders, total_smart_money_shares,
    total_smart_money_value_usd, quarter_change, notable_holders,
    new_positions, exited_positions.
    """
    no_data = {
        "has_data": False,
        "smart_money_holders": 0,
        "total_smart_money_shares": 0,
        "total_smart_money_value_usd": 0,
        "quarter_change": None,
        "notable_holders": [],
        "new_positions": [],
        "exited_positions": [],
    }

    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM fund_holdings LIMIT 1")
    except Exception:
        conn.rollback()
        return no_data

    # Get the two most recent quarters for this ticker
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT quarter FROM fund_holdings
        WHERE ticker = %s AND ticker != ''
        ORDER BY quarter DESC
        LIMIT 2
    """, (ticker,))
    quarters = cur.fetchall()

    if not quarters:
        return no_data

    latest_q = quarters[0][0]
    prev_q = quarters[1][0] if len(quarters) > 1 else None

    # Latest quarter holdings
    cur.execute("""
        SELECT fund_name, fund_cik, shares, value_usd
        FROM fund_holdings
        WHERE ticker = %s AND quarter = %s
    """, (ticker, latest_q))
    latest_rows = cur.fetchall()

    if not latest_rows:
        return no_data

    total_shares = 0.0
    total_value = 0.0
    holders = []

    for fund_name, fund_cik, shares, value_usd in latest_rows:
        holders.append(fund_name)
        if shares:
            total_shares += shares
        if value_usd:
            total_value += value_usd

    # Compare with previous quarter if available
    quarter_change = None
    new_positions = []
    exited_positions = []

    if prev_q:
        cur.execute("""
            SELECT fund_name, fund_cik, shares
            FROM fund_holdings
            WHERE ticker = %s AND quarter = %s
        """, (ticker, prev_q))
        prev_rows = cur.fetchall()

        prev_holders = {r[0] for r in prev_rows}
        latest_holders = {r[0] for r in latest_rows}
        prev_total = sum(r[2] for r in prev_rows if r[2])

        new_positions = sorted(latest_holders - prev_holders)
        exited_positions = sorted(prev_holders - latest_holders)

        if prev_total > 0:
            quarter_change = round(total_shares - prev_total)

    return {
        "has_data": True,
        "smart_money_holders": len(holders),
        "total_smart_money_shares": round(total_shares),
        "total_smart_money_value_usd": round(total_value),
        "quarter_change": quarter_change,
        "notable_holders": sorted(set(holders)),
        "new_positions": new_positions,
        "exited_positions": exited_positions,
    }
