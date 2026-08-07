#!/usr/bin/env python3
"""
Refresh `price_history` for tickers in `current_stock_data`.

Usage
-----
uv run python scripts/update_price_history_current.py
uv run python scripts/update_price_history_current.py --limit 50
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from invest.data.db import get_connection


def load_tickers(conn, limit: int | None = None) -> list[str]:
    """Load tickers from current_stock_data."""
    cursor = conn.cursor()
    if limit is not None and limit > 0:
        cursor.execute(
            'SELECT ticker FROM current_stock_data WHERE current_price IS NOT NULL ORDER BY ticker LIMIT %s',
            (int(limit),),
        )
    else:
        cursor.execute('SELECT ticker FROM current_stock_data WHERE current_price IS NOT NULL ORDER BY ticker')
    return [row[0] for row in cursor.fetchall()]


def upsert_price_history(conn, ticker: str, period: str) -> int:
    """
    Fetch and save historical prices for one ticker.

    Parameters
    ----------
    conn
        DB connection.
    ticker : str
        Stock ticker.
    period : str
        yfinance period string.

    Returns
    -------
    int
        Number of rows inserted/replaced.
    """
    history = yf.Ticker(ticker).history(period=period, auto_adjust=False)
    if history.empty:
        return 0

    cursor = conn.cursor()
    count = 0
    for date, row in history.iterrows():
        cursor.execute(
            '''
            INSERT INTO price_history (
                ticker, date, open, high, low, close, volume, dividends, stock_splits, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (ticker, date) DO UPDATE SET
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                dividends = EXCLUDED.dividends,
                stock_splits = EXCLUDED.stock_splits,
                created_at = EXCLUDED.created_at
            ''',
            (
                ticker,
                date.strftime('%Y-%m-%d'),
                float(row['Open']) if row.get('Open') is not None else None,
                float(row['High']) if row.get('High') is not None else None,
                float(row['Low']) if row.get('Low') is not None else None,
                float(row['Close']) if row.get('Close') is not None else None,
                float(row['Volume']) if row.get('Volume') is not None else None,
                float(row['Dividends']) if row.get('Dividends') is not None else None,
                float(row['Stock Splits']) if row.get('Stock Splits') is not None else None,
                datetime.now().isoformat(),
            ),
        )
        count += 1

    conn.commit()
    return count


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description='Refresh price_history from yfinance')
    parser.add_argument('--period', default='5y', help='yfinance period, e.g. 2y, 5y, 10y')
    parser.add_argument('--limit', type=int, default=None, help='Max tickers to refresh')
    parser.add_argument('--sleep', type=float, default=0.1, help='Delay between ticker requests')
    args = parser.parse_args()

    conn = get_connection()

    tickers = load_tickers(conn, limit=args.limit)
    print(f'Refreshing price history for {len(tickers)} tickers (period={args.period})')

    total_rows = 0
    success = 0
    failed = 0
    for i, ticker in enumerate(tickers, start=1):
        try:
            inserted = upsert_price_history(conn, ticker, period=args.period)
            total_rows += inserted
            success += 1
            if i % 25 == 0:
                print(f'  [{i}/{len(tickers)}] {ticker} rows={inserted}')
        except Exception as exc:
            failed += 1
            print(f'  [{i}/{len(tickers)}] {ticker} failed: {exc}')
        time.sleep(max(args.sleep, 0.0))

    conn.close()
    print(f'Completed. Success={success}, Failed={failed}, Rows saved={total_rows}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
