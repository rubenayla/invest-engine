"""
Politician Trade Database — schema, storage, and signal computation.

Stores congressional periodic transaction reports (PTRs) from the House
financial disclosure system and computes aggregate politician-trade signals
(recent buy/sell counts, top-politician weighting, recency).

PTRs have a disclosure lag of up to 45 days, so this is a watchlist trigger
— surface candidates for further research, not a market-timing signal.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Set, Tuple

import psycopg2.extensions

logger = logging.getLogger(__name__)

# Politicians whose trades have shown the strongest historical signal.
# Multiplier applied when computing weighted signal score, keyed on
# (politician_name, transaction_type) where transaction_type is 'P'
# (Purchase) or 'S' (Sale). Splitting by direction lets us amplify or
# fade a politician's signal independently per side.
#
# Weights from notes/research/politician_backtest_2026.md (Tuberville split).
# Other politicians use uniform weights pending individual backtest.
HIGH_SIGNAL_POLITICIANS: Dict[Tuple[str, str], float] = {
    # Pelosi — uniform pending direction-split backtest
    ('Pelosi, Nancy', 'P'): 3.0,
    ('Pelosi, Nancy', 'S'): 3.0,
    # Tuberville — backtest 2026: buys −9% alpha @180d (n=118, p=0.003),
    # sells +14% alpha @365d (n=216, hit 75.5%, p<0.001). Fade buys, ride sells.
    ('Tuberville, Tommy', 'P'): 0.3,
    ('Tuberville, Tommy', 'S'): 3.5,
    # Crenshaw — uniform pending individual backtest
    ('Crenshaw, Dan', 'P'): 1.5,
    ('Crenshaw, Dan', 'S'): 1.5,
    # Gottheimer — uniform pending individual backtest
    ('Gottheimer, Josh', 'P'): 1.5,
    ('Gottheimer, Josh', 'S'): 1.5,
}

# Default weight for politicians not in the high-signal dict.
DEFAULT_POLITICIAN_WEIGHT: float = 1.0


def _politician_weight(name: str, tx_type: str | None) -> float:
    """Look up signal weight for a (politician, transaction_type) pair.

    transaction_type is normalized to its first letter uppercased
    ('P' for Purchase, 'S' for Sale, 'E' for Exchange) before lookup,
    matching how compute_politician_signal classifies trades.
    """
    if not tx_type:
        return DEFAULT_POLITICIAN_WEIGHT
    code = tx_type.strip().upper()[:1]
    return HIGH_SIGNAL_POLITICIANS.get((name, code), DEFAULT_POLITICIAN_WEIGHT)


def _gate_aware_weight(name: str, tx_type: str | None) -> float:
    """Politician weight with the gate registry applied as a filter.

    Layers `src/invest/signals/gates.py:SIGNAL_GATES` on top of the
    manual weight in `HIGH_SIGNAL_POLITICIANS`:
      - Backtested PASS  → keep the manual weight (signal is real).
      - Backtested FAIL  → return 0 (signal is noise or wrong-direction).
      - UNGATED          → keep the manual weight (haven't measured;
                           preserves today's behavior for the long tail).
    Result: politicians like Gottheimer (FAIL both directions) and
    Pelosi sells (FAIL) stop contributing to the catalyst score, while
    Pelosi buys and Tuberville sells contribute at their full weight.
    """
    base = _politician_weight(name, tx_type)
    if not tx_type:
        return base
    code = tx_type.strip().upper()[:1]
    # Imported lazily so the politician-data layer doesn't depend on
    # the signals layer at module import time.
    from invest.signals.gates import evaluate

    gate = evaluate('politician', name, code)
    if gate is None:
        return base  # UNGATED — preserve manual weight
    if not gate.passes:
        return 0.0  # FAIL — drop contribution
    return base  # PASS — keep manual weight


def ensure_schema(conn) -> None:
    """Create politician_trades tables if they don't exist."""
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS politician_trades (
            id SERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            politician_name TEXT NOT NULL,
            party TEXT,
            chamber TEXT NOT NULL,
            state_district TEXT,
            transaction_date TEXT NOT NULL,
            disclosure_date TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            amount_min REAL,
            amount_max REAL,
            asset_description TEXT,
            doc_id TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT 'house_clerk',
            UNIQUE(doc_id, ticker, politician_name, transaction_date, transaction_type, amount_min)
        )
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_politician_ticker
            ON politician_trades(ticker)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_politician_ticker_date
            ON politician_trades(ticker, transaction_date)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_politician_disclosure_date
            ON politician_trades(disclosure_date)
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS politician_trades_fetch_log (
            doc_id TEXT PRIMARY KEY,
            politician_name TEXT NOT NULL,
            chamber TEXT NOT NULL,
            year INTEGER,
            fetched_at TEXT NOT NULL,
            transaction_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ok'
        )
    """)
    conn.commit()


def get_known_doc_ids(conn, year: int | None = None) -> Set[str]:
    """Return doc_ids already processed (success or skip)."""
    try:
        cur = conn.cursor()
        if year is None:
            cur.execute("SELECT doc_id FROM politician_trades_fetch_log")
        else:
            cur.execute(
                "SELECT doc_id FROM politician_trades_fetch_log WHERE year = %s",
                (year,),
            )
        return {row[0] for row in cur.fetchall()}
    except Exception:
        conn.rollback()
        return set()


def insert_trades(conn, trades: List[Dict[str, Any]]) -> int:
    """Insert trades, ignoring duplicates. Returns count inserted.

    Uses per-row savepoints so a single bad row doesn't roll back the batch.
    """
    inserted = 0
    cur = conn.cursor()
    for idx, t in enumerate(trades):
        sp = f'sp_pt_{idx}'
        cur.execute(f'SAVEPOINT {sp}')
        try:
            cur.execute("""
                INSERT INTO politician_trades
                (ticker, politician_name, party, chamber, state_district,
                 transaction_date, disclosure_date, transaction_type,
                 amount_min, amount_max, asset_description, doc_id, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                t['ticker'], t['politician_name'], t.get('party'),
                t['chamber'], t.get('state_district'),
                t['transaction_date'], t['disclosure_date'],
                t['transaction_type'],
                t.get('amount_min'), t.get('amount_max'),
                t.get('asset_description'), t['doc_id'],
                t.get('source', 'house_clerk'),
            ))
            inserted += cur.rowcount
            cur.execute(f'RELEASE SAVEPOINT {sp}')
        except Exception as exc:
            logger.debug('insert_trades row failed (%s): %s', t.get('ticker'), exc)
            cur.execute(f'ROLLBACK TO SAVEPOINT {sp}')
    conn.commit()
    return inserted


def log_doc(
    conn,
    doc_id: str,
    politician_name: str,
    chamber: str,
    year: int | None,
    transaction_count: int,
    status: str = 'ok',
) -> None:
    """Record that a doc_id has been processed."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO politician_trades_fetch_log
        (doc_id, politician_name, chamber, year, fetched_at, transaction_count, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (doc_id) DO UPDATE SET
            fetched_at = EXCLUDED.fetched_at,
            transaction_count = EXCLUDED.transaction_count,
            status = EXCLUDED.status
    """, (
        doc_id, politician_name, chamber, year,
        datetime.utcnow().isoformat(), transaction_count, status,
    ))
    conn.commit()


def _no_politician_data() -> Dict[str, Any]:
    """Fresh "no politician activity" signal dict (one per ticker, never shared)."""
    return {
        'has_data': False,
        'buy_count': 0,
        'sell_count': 0,
        'weighted_score': 0.0,
        'top_politicians': [],
        'recency_days': None,
    }


def _aggregate_politician_rows(rows) -> Dict[str, Any]:
    """
    Aggregate one ticker's trade rows into a politician signal dict.

    `rows` are tuples of (politician_name, transaction_type, transaction_date,
    amount_min, amount_max) ordered by date DESC. Assumes `rows` is non-empty.
    """
    buy_count = 0
    sell_count = 0
    weighted_score = 0.0
    politician_activity: Dict[str, Dict[str, Any]] = {}
    last_trade_date: str | None = None

    for name, tx_type, tx_date, amt_min, amt_max in rows:
        if last_trade_date is None:
            last_trade_date = tx_date

        weight = _gate_aware_weight(name, tx_type)
        size_factor = _amount_size_factor(amt_min, amt_max)

        is_buy = tx_type and tx_type.upper().startswith('P')  # Purchase
        is_sell = tx_type and tx_type.upper().startswith('S')  # Sale (full/partial)

        if is_buy:
            buy_count += 1
            weighted_score += weight * size_factor
        elif is_sell:
            sell_count += 1
            weighted_score -= weight * size_factor

        # Track the highest weight seen so far for this politician across
        # directions — used purely for ranking in top_politicians.
        entry = politician_activity.setdefault(
            name, {'name': name, 'buys': 0, 'sells': 0, 'weight': weight}
        )
        if weight > entry['weight']:
            entry['weight'] = weight
        if is_buy:
            entry['buys'] += 1
        elif is_sell:
            entry['sells'] += 1

    recency_days = None
    if last_trade_date:
        try:
            last_dt = datetime.strptime(last_trade_date, '%Y-%m-%d')
            recency_days = (datetime.utcnow() - last_dt).days
        except ValueError:
            pass

    top_politicians = sorted(
        politician_activity.values(),
        key=lambda e: (e['weight'], e['buys'] + e['sells']),
        reverse=True,
    )[:5]

    return {
        'has_data': True,
        'buy_count': buy_count,
        'sell_count': sell_count,
        'weighted_score': round(weighted_score, 2),
        'top_politicians': top_politicians,
        'recency_days': recency_days,
    }


def compute_politician_signal(
    conn,
    ticker: str,
    lookback_days: int = 180,
) -> Dict[str, Any]:
    """
    Compute aggregate politician-trade signal for a ticker.

    Returns dict with: buy_count, sell_count, weighted_score (positive=net
    buying weighted by politician), top_politicians, recency_days, has_data.
    """
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
        cur.execute('SELECT 1 FROM politician_trades LIMIT 1')
    except Exception:
        conn.rollback()
        return _no_politician_data()

    cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
    cur.execute("""
        SELECT politician_name, transaction_type, transaction_date,
               amount_min, amount_max
        FROM politician_trades
        WHERE ticker = %s AND transaction_date >= %s
        ORDER BY transaction_date DESC
    """, (ticker, cutoff))
    rows = cur.fetchall()

    if not rows:
        return _no_politician_data()

    return _aggregate_politician_rows(rows)


def compute_all_politician_signals(
    conn,
    lookback_days: int = 180,
) -> Dict[str, Dict[str, Any]]:
    """
    Batch equivalent of compute_politician_signal for every ticker in one query.

    Returns {ticker: signal_dict}. Tickers with no recent trades are omitted;
    callers should default those to _no_politician_data().
    """
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
        cur.execute('SELECT 1 FROM politician_trades LIMIT 1')
    except Exception:
        conn.rollback()
        return {}

    cutoff = (datetime.utcnow() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')
    cur = conn.cursor(cursor_factory=psycopg2.extensions.cursor)
    cur.execute("""
        SELECT ticker, politician_name, transaction_type, transaction_date,
               amount_min, amount_max
        FROM politician_trades
        WHERE transaction_date >= %s
        ORDER BY ticker, transaction_date DESC
    """, (cutoff,))
    rows_by_ticker: Dict[str, list] = {}
    for r in cur.fetchall():
        rows_by_ticker.setdefault(r[0], []).append(r[1:])

    return {tk: _aggregate_politician_rows(rows) for tk, rows in rows_by_ticker.items()}


def _amount_size_factor(amt_min: float | None, amt_max: float | None) -> float:
    """Map disclosed amount range to a 0.5–2.0 size factor (log-ish)."""
    if amt_min is None and amt_max is None:
        return 1.0
    midpoint = ((amt_min or 0) + (amt_max or amt_min or 0)) / 2
    if midpoint <= 15_000:
        return 0.5
    if midpoint <= 50_000:
        return 1.0
    if midpoint <= 250_000:
        return 1.5
    return 2.0
