#!/usr/bin/env python3
"""
Fetch and store macro risk-free rates in PostgreSQL.

Usage
-----
uv run python scripts/update_macro_rates.py
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from invest.data.db import get_connection


RATE_SERIES: Dict[str, Dict[str, str]] = {
    'risk_free_rate': {
        'ticker': '^IRX',
        'description': '13-week T-bill proxy for risk-free rate',
    },
    'risk_free_10y': {
        'ticker': '^TNX',
        'description': '10-year treasury yield proxy',
    },
}


def ensure_macro_rates_table(conn) -> None:
    """Create macro_rates table if needed."""
    cursor = conn.cursor()
    cursor.execute(
        '''
        CREATE TABLE IF NOT EXISTS macro_rates (
            rate_name TEXT NOT NULL,
            date DATE NOT NULL,
            value REAL NOT NULL,
            source TEXT,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (rate_name, date)
        )
        '''
    )
    cursor.execute(
        '''
        CREATE INDEX IF NOT EXISTS idx_macro_rates_rate_date
        ON macro_rates(rate_name, date DESC)
        '''
    )
    conn.commit()


def fetch_series(symbol: str, period: str) -> list[tuple[str, float]]:
    """
    Fetch and normalize yield series from yfinance.

    Parameters
    ----------
    symbol : str
        Yahoo Finance symbol.
    period : str
        yfinance period.

    Returns
    -------
    list[tuple[str, float]]
        List of (date, decimal_rate).
    """
    history = yf.Ticker(symbol).history(period=period, auto_adjust=False)
    if history.empty:
        return []

    rows: list[tuple[str, float]] = []
    for date, row in history.iterrows():
        close = row.get('Close')
        if close is None:
            continue
        try:
            value = float(close) / 100.0
        except (TypeError, ValueError):
            continue

        if value <= -1 or value >= 1:
            continue

        rows.append((date.strftime('%Y-%m-%d'), value))

    return rows


def save_series(
    conn,
    rate_name: str,
    rows: list[tuple[str, float]],
    source: str,
) -> int:
    """
    Save normalized macro rows.

    Parameters
    ----------
    conn
        DB connection.
    rate_name : str
        Rate name key.
    rows : list[tuple[str, float]]
        Date/value tuples.
    source : str
        Source label.

    Returns
    -------
    int
        Number of rows saved.
    """
    if not rows:
        return 0

    cursor = conn.cursor()
    for date_value in rows:
        cursor.execute(
            '''
            INSERT INTO macro_rates (rate_name, date, value, source, fetched_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (rate_name, date) DO UPDATE SET
                value = EXCLUDED.value,
                source = EXCLUDED.source,
                fetched_at = EXCLUDED.fetched_at
            ''',
            (rate_name, date_value[0], date_value[1], source, datetime.now().isoformat()),
        )
    conn.commit()
    return len(rows)


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description='Update macro risk-free rates in PostgreSQL')
    parser.add_argument('--period', default='5y', help='yfinance period (e.g., 1y, 5y, 10y)')
    args = parser.parse_args()

    conn = get_connection()

    ensure_macro_rates_table(conn)

    total_saved = 0
    print('Updating macro rates...')
    for rate_name, spec in RATE_SERIES.items():
        symbol = spec['ticker']
        rows = fetch_series(symbol, period=args.period)
        saved = save_series(conn, rate_name, rows, f'yfinance:{symbol}')
        total_saved += saved
        print(f'  {rate_name:16s} {symbol:6s} saved={saved:4d}')

    conn.close()
    print(f'Completed. Total rows saved: {total_saved}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
