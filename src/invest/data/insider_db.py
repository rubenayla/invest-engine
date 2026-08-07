"""
Insider Transaction Database — schema, storage, and signal computation.

Stores Form 4 insider transactions and computes aggregate insider signals
(net buy %, cluster score, recency, dollar conviction).
"""

import logging
import psycopg2
import psycopg2.extensions
import psycopg2.extras
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "stock_data.db"


def ensure_schema(conn) -> None:
    """Create insider tables if they don't exist."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS insider_transactions (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            cik TEXT NOT NULL,
            accession_number TEXT NOT NULL,
            filing_date TEXT NOT NULL,
            transaction_date TEXT NOT NULL,
            reporter_name TEXT NOT NULL,
            reporter_title TEXT,
            transaction_type TEXT NOT NULL,
            shares REAL NOT NULL,
            price_per_share REAL,
            shares_owned_after REAL,
            is_open_market INTEGER DEFAULT 0,
            UNIQUE(accession_number, reporter_name, transaction_date, shares)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_insider_ticker
            ON insider_transactions(ticker)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_insider_ticker_date
            ON insider_transactions(ticker, transaction_date)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS insider_fetch_log (
            ticker TEXT PRIMARY KEY,
            cik TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            form4_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ok'
        )
    """)
    conn.commit()


def insert_transactions(conn, transactions: List[Dict[str, Any]]) -> int:
    """Insert transactions, ignoring duplicates. Returns count inserted."""
    inserted = 0
    cur = conn.cursor()
    for txn in transactions:
        try:
            cur.execute("""
                INSERT INTO insider_transactions
                (ticker, cik, accession_number, filing_date, transaction_date,
                 reporter_name, reporter_title, transaction_type, shares,
                 price_per_share, shares_owned_after, is_open_market)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                txn["ticker"], txn["cik"], txn["accession_number"],
                txn["filing_date"], txn["transaction_date"],
                txn["reporter_name"], txn.get("reporter_title", ""),
                txn["transaction_type"], txn["shares"],
                txn.get("price_per_share"), txn.get("shares_owned_after"),
                txn.get("is_open_market", 0),
            ))
            inserted += cur.rowcount
        except Exception:
            conn.rollback()
    conn.commit()
    return inserted


def log_fetch(conn, ticker: str, cik: str,
              form4_count: int, status: str = "ok") -> None:
    """Record that we fetched insider data for a ticker."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO insider_fetch_log (ticker, cik, fetched_at, form4_count, status)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (ticker) DO UPDATE SET
            cik = EXCLUDED.cik,
            fetched_at = EXCLUDED.fetched_at,
            form4_count = EXCLUDED.form4_count,
            status = EXCLUDED.status
    """, (ticker, cik, datetime.utcnow().isoformat(), form4_count, status))
    conn.commit()


def get_known_accessions(conn, ticker: str) -> Set[str]:
    """Get set of accession numbers already stored for a ticker."""
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT accession_number FROM insider_transactions WHERE ticker = %s",
            (ticker,)
        )
        rows = cur.fetchall()
        return {r[0] for r in rows}
    except Exception:
        conn.rollback()
        return set()


def _no_insider_data() -> Dict[str, Any]:
    """Fresh "no insider activity" signal dict (one per ticker, never shared)."""
    return {
        "has_data": False,
        "net_buy_pct": 0.0,
        "cluster_score": 0,
        "recency_days": None,
        "dollar_conviction": 0.0,
        "buy_count": 0,
        "sell_count": 0,
        "sell_trend": None,  # ratio vs historical avg (0.5 = half normal selling)
        "buy_trend": None,
    }


def _aggregate_insider_rows(rows) -> Dict[str, Any]:
    """
    Aggregate one ticker's recent open-market rows into a signal dict
    (without the historical sell/buy trends, which the caller fills in).

    `rows` are tuples of (transaction_type, shares, price_per_share,
    transaction_date, reporter_name, is_open_market) ordered by date DESC.
    Assumes `rows` is non-empty.
    """
    buy_shares = 0.0
    sell_shares = 0.0
    buy_dollars = 0.0
    buy_count = 0
    sell_count = 0
    last_buy_date = None
    buy_events: List[Dict[str, Any]] = []  # for cluster calculation

    for tx_type, shares, price, tx_date, reporter, is_om in rows:
        if tx_type == "P":
            buy_shares += shares
            buy_count += 1
            if price:
                buy_dollars += shares * price
            if last_buy_date is None:
                last_buy_date = tx_date
            buy_events.append({"date": tx_date, "reporter": reporter})
        elif tx_type == "S":
            sell_shares += shares
            sell_count += 1

    # Net buy % (relative to total traded volume as proxy)
    total_shares = buy_shares + sell_shares
    net_buy_pct = ((buy_shares - sell_shares) / total_shares * 100) if total_shares > 0 else 0.0

    # Cluster score: max distinct insiders buying in any 30-day window
    cluster_score = _compute_cluster_score(buy_events)

    # Recency: days since last open-market purchase
    recency_days = None
    if last_buy_date:
        try:
            last_dt = datetime.strptime(last_buy_date, "%Y-%m-%d")
            recency_days = (datetime.utcnow() - last_dt).days
        except ValueError:
            pass

    return {
        "has_data": True,
        "net_buy_pct": round(net_buy_pct, 2),
        "cluster_score": cluster_score,
        "recency_days": recency_days,
        "dollar_conviction": round(buy_dollars, 2),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "sell_trend": None,
        "buy_trend": None,
    }


def _trends_from_aggregates(earliest_date_str, total_count,
                            recent_sells, recent_buys, prior_sells, prior_buys,
                            lookback_days, now) -> tuple:
    """
    Pure trend math shared by the single-ticker and batch paths.

    Returns (sell_trend, buy_trend), each a ratio vs the historical average
    rate (0.5 = half normal, 2.0 = double), or None when there is not enough
    history to form a baseline.
    """
    if not earliest_date_str or total_count < 3:
        return None, None
    try:
        earliest_date = datetime.strptime(earliest_date_str, "%Y-%m-%d")
    except (ValueError, TypeError):
        return None, None

    total_history_days = (now - earliest_date).days
    # Need at least 1.5x the lookback period to have a meaningful baseline
    if total_history_days < lookback_days * 1.5:
        return None, None

    prior_days = max(total_history_days - lookback_days, 1)

    sell_trend = None
    if prior_sells > 0:
        prior_sell_rate = prior_sells / prior_days * lookback_days
        sell_trend = round(recent_sells / prior_sell_rate, 2) if prior_sell_rate > 0 else None

    buy_trend = None
    if prior_buys > 0:
        prior_buy_rate = prior_buys / prior_days * lookback_days
        buy_trend = round(recent_buys / prior_buy_rate, 2) if prior_buy_rate > 0 else None

    return sell_trend, buy_trend


def compute_insider_signal(conn, ticker: str,
                           lookback_days: int = 180) -> Dict[str, Any]:
    """
    Compute aggregate insider activity signal for a ticker.

    Returns dict with: net_buy_pct, cluster_score, recency_days,
    dollar_conviction, buy_count, sell_count, has_data.
    """
    # Check table exists
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
        cur.execute("SELECT 1 FROM insider_transactions LIMIT 1")
    except Exception:
        conn.rollback()
        return _no_insider_data()

    cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    # Use a plain cursor (not dict) since we unpack by position below
    cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
    cur.execute("""
        SELECT transaction_type, shares, price_per_share, transaction_date,
               reporter_name, is_open_market
        FROM insider_transactions
        WHERE ticker = %s AND transaction_date >= %s AND is_open_market = 1
        ORDER BY transaction_date DESC
    """, (ticker, cutoff))
    rows = cur.fetchall()

    if not rows:
        return _no_insider_data()

    signal = _aggregate_insider_rows(rows)
    sell_trend, buy_trend = _compute_activity_trends(conn, ticker, lookback_days)
    signal["sell_trend"] = sell_trend
    signal["buy_trend"] = buy_trend
    return signal


def compute_all_insider_signals(conn, lookback_days: int = 180) -> Dict[str, Dict[str, Any]]:
    """
    Batch equivalent of compute_insider_signal for every ticker in one pass.

    Replaces ~4 queries-per-ticker with 3 total queries, returning
    {ticker: signal_dict}. Tickers with no recent open-market activity are
    omitted; callers should default those to _no_insider_data().
    """
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
        cur.execute("SELECT 1 FROM insider_transactions LIMIT 1")
    except Exception:
        conn.rollback()
        return {}

    now = datetime.utcnow()
    cutoff = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    # 1) Recent open-market rows for all tickers (drives main aggregation).
    cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
    cur.execute("""
        SELECT ticker, transaction_type, shares, price_per_share, transaction_date,
               reporter_name, is_open_market
        FROM insider_transactions
        WHERE transaction_date >= %s AND is_open_market = 1
        ORDER BY ticker, transaction_date DESC
    """, (cutoff,))
    rows_by_ticker: Dict[str, list] = {}
    for r in cur.fetchall():
        rows_by_ticker.setdefault(r[0], []).append(r[1:])

    # 2) Full-history earliest date + count per ticker (trend baseline gate).
    cur.execute("""
        SELECT ticker, MIN(transaction_date), COUNT(*)
        FROM insider_transactions
        WHERE is_open_market = 1
        GROUP BY ticker
    """)
    history = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    # 3) Full-history recent-vs-prior buy/sell counts per ticker.
    cur.execute("""
        SELECT ticker, transaction_type,
               CASE WHEN transaction_date >= %s THEN 'recent' ELSE 'prior' END AS period,
               COUNT(*) AS cnt
        FROM insider_transactions
        WHERE is_open_market = 1
        GROUP BY ticker, transaction_type, period
    """, (cutoff,))
    trend_counts: Dict[str, Dict[str, int]] = {}
    for tk, tx_type, period, cnt in cur.fetchall():
        d = trend_counts.setdefault(
            tk, {"recent_sells": 0, "recent_buys": 0, "prior_sells": 0, "prior_buys": 0}
        )
        if period == "recent":
            if tx_type == "S":
                d["recent_sells"] = cnt
            elif tx_type == "P":
                d["recent_buys"] = cnt
        else:
            if tx_type == "S":
                d["prior_sells"] = cnt
            elif tx_type == "P":
                d["prior_buys"] = cnt

    signals: Dict[str, Dict[str, Any]] = {}
    for ticker, rows in rows_by_ticker.items():
        signal = _aggregate_insider_rows(rows)
        earliest_date_str, total_count = history.get(ticker, (None, 0))
        tc = trend_counts.get(ticker, {})
        sell_trend, buy_trend = _trends_from_aggregates(
            earliest_date_str, total_count,
            tc.get("recent_sells", 0), tc.get("recent_buys", 0),
            tc.get("prior_sells", 0), tc.get("prior_buys", 0),
            lookback_days, now,
        )
        signal["sell_trend"] = sell_trend
        signal["buy_trend"] = buy_trend
        signals[ticker] = signal
    return signals


def _compute_activity_trends(conn, ticker: str, lookback_days: int) -> tuple:
    """
    Compare recent sell/buy counts to the historical average rate.

    Returns (sell_trend, buy_trend) where each is a ratio vs historical avg.
    e.g. 0.5 = half the normal rate, 2.0 = double the normal rate.
    None if insufficient historical data to compute a baseline.
    """
    now = datetime.utcnow()
    recent_cutoff = (now - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

    # Get the full date range of data for this ticker
    # Use a plain cursor (not dict) since we unpack by position below
    cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
    cur.execute("""
        SELECT MIN(transaction_date), COUNT(*) FROM insider_transactions
        WHERE ticker = %s AND is_open_market = 1
    """, (ticker,))
    row = cur.fetchone()

    if not row or not row[0] or row[1] < 3:
        return None, None

    earliest_date_str = row[0]
    total_count = row[1]

    # Count sells and buys in recent period vs all prior history
    cur.execute("""
        SELECT
            transaction_type,
            CASE WHEN transaction_date >= %s THEN 'recent' ELSE 'prior' END AS period,
            COUNT(*) as cnt
        FROM insider_transactions
        WHERE ticker = %s AND is_open_market = 1
        GROUP BY transaction_type, period
    """, (recent_cutoff, ticker))
    counts = cur.fetchall()

    recent_sells = 0
    recent_buys = 0
    prior_sells = 0
    prior_buys = 0
    for tx_type, period, cnt in counts:
        if period == "recent":
            if tx_type == "S":
                recent_sells = cnt
            elif tx_type == "P":
                recent_buys = cnt
        else:
            if tx_type == "S":
                prior_sells = cnt
            elif tx_type == "P":
                prior_buys = cnt

    return _trends_from_aggregates(
        earliest_date_str, total_count,
        recent_sells, recent_buys, prior_sells, prior_buys,
        lookback_days, now,
    )


def _compute_cluster_score(buy_events: List[Dict[str, Any]]) -> int:
    """Max distinct insiders buying in any 30-day rolling window."""
    if not buy_events:
        return 0

    dated_events = []
    for ev in buy_events:
        try:
            dt = datetime.strptime(ev["date"], "%Y-%m-%d")
            dated_events.append((dt, ev["reporter"]))
        except ValueError:
            continue

    if not dated_events:
        return 0

    dated_events.sort(key=lambda x: x[0])
    max_distinct = 0

    for i, (dt_i, _) in enumerate(dated_events):
        window_end = dt_i + timedelta(days=30)
        reporters_in_window = set()
        for dt_j, reporter in dated_events[i:]:
            if dt_j <= window_end:
                reporters_in_window.add(reporter)
            else:
                break
        max_distinct = max(max_distinct, len(reporters_in_window))

    return max_distinct
