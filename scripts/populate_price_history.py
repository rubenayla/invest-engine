#!/usr/bin/env python3
"""
Populate price_history table for all snapshots.

This script:
1. Finds all snapshots missing price_history data
2. Fetches historical prices from yfinance
3. Saves them to the price_history table

Usage:
    uv run python scripts/populate_price_history.py
    uv run python scripts/populate_price_history.py --ticker AAPL  # Single ticker
    uv run python scripts/populate_price_history.py --limit 100     # Limit stocks
"""

import argparse
import logging
import sys
from datetime import timedelta
from pathlib import Path
from typing import Optional

import pandas as pd
import yfinance as yf

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
sys.path.insert(0, str(Path(__file__).parent.parent))

from invest.data.db import get_connection

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PriceHistoryPopulator:
    """Populates price_history table for snapshots."""

    def __init__(self, db_path: str = None):
        pass  # connections come from get_connection()

    def get_snapshots_needing_prices(self, ticker: Optional[str] = None, limit: Optional[int] = None):
        """
        Get snapshots that need price_history populated.

        Parameters
        ----------
        ticker : str, optional
            If provided, only get snapshots for this ticker
        limit : int, optional
            Maximum number of snapshots to return

        Returns
        -------
        list of dict
            List of snapshots needing price data, each with keys:
            - snapshot_id
            - ticker
            - snapshot_date
        """
        conn = get_connection()
        cursor = conn.cursor()

        # Build query with parameterized values
        params = []
        ticker_filter = ''
        if ticker:
            ticker_filter = 'AND a.symbol = %s'
            params.append(ticker)
        limit_clause = ''
        if limit:
            limit_clause = 'LIMIT %s'
            params.append(limit)

        query = f'''
            SELECT
                s.id as snapshot_id,
                a.symbol as ticker,
                s.snapshot_date
            FROM fundamental_history s
            JOIN assets a ON s.asset_id = a.id
            WHERE s.vix IS NOT NULL
            AND NOT EXISTS (
                SELECT 1 FROM price_history ph
                WHERE ph.ticker = a.symbol
                AND ph.date = s.snapshot_date::date
            )
            {ticker_filter}
            ORDER BY a.symbol, s.snapshot_date
            {limit_clause}
        '''

        cursor.execute(query, params)
        results = [
            {
                'snapshot_id': row[0],
                'ticker': row[1],
                'snapshot_date': row[2]
            }
            for row in cursor.fetchall()
        ]

        conn.close()
        return results

    def fetch_and_save_price_history(self, snapshot_id: int, ticker: str, snapshot_date: str) -> bool:
        """
        Fetch historical prices and save to price_history table.

        Parameters
        ----------
        snapshot_id : int
            ID of the snapshot to link prices to
        ticker : str
            Stock ticker symbol
        snapshot_date : str
            Date of the snapshot (YYYY-MM-DD format)

        Returns
        -------
        bool
            True if successful, False otherwise
        """
        try:
            # Parse snapshot date (make timezone-naive for comparison)
            snap_dt = pd.Timestamp(snapshot_date).tz_localize(None)

            # Fetch prices from 3 years before snapshot date to snapshot date
            start_date = snap_dt - timedelta(days=3*365)
            end_date = snap_dt + timedelta(days=1)  # Include snapshot date

            logger.info(f'{ticker} (snapshot {snapshot_id}): Fetching prices from {start_date.date()} to {snap_dt.date()}')

            # Fetch from yfinance
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date, auto_adjust=False)

            if hist.empty:
                logger.warning(f'{ticker}: No price data available')
                return False

            # Convert index to timezone-naive for comparison
            hist.index = hist.index.tz_localize(None)

            # Filter to only dates <= snapshot_date
            hist = hist[hist.index <= snap_dt]

            if hist.empty:
                logger.warning(f'{ticker}: No price data before or on snapshot date {snapshot_date}')
                return False

            logger.info(f'{ticker}: Found {len(hist)} price records')

            # Save to database
            conn = get_connection()
            cursor = conn.cursor()

            inserted = 0
            for date, row in hist.iterrows():
                try:
                    cursor.execute('''
                        INSERT INTO price_history (
                            ticker, date, open, high, low, close,
                            volume, dividends, stock_splits
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                    ''', (
                        ticker,
                        date.strftime('%Y-%m-%d'),
                        float(row['Open']) if pd.notna(row['Open']) else None,
                        float(row['High']) if pd.notna(row['High']) else None,
                        float(row['Low']) if pd.notna(row['Low']) else None,
                        float(row['Close']) if pd.notna(row['Close']) else None,
                        int(row['Volume']) if pd.notna(row['Volume']) else None,
                        float(row['Dividends']) if pd.notna(row['Dividends']) else None,
                        float(row['Stock Splits']) if pd.notna(row['Stock Splits']) else None
                    ))
                    inserted += 1
                except Exception as e:
                    logger.warning(f'{ticker} {date}: Failed to insert: {e}')

            conn.commit()
            conn.close()

            logger.info(f'{ticker} (snapshot {snapshot_id}): Inserted {inserted} price records')
            return True

        except Exception as e:
            logger.error(f'{ticker} (snapshot {snapshot_id}): Failed to fetch/save prices: {e}')
            return False


def main():
    """Populate price_history for snapshots."""
    parser = argparse.ArgumentParser(description='Populate price_history for snapshots')
    parser.add_argument('--ticker', help='Populate for specific ticker only')
    parser.add_argument('--limit', type=int, help='Limit number of snapshots to process')
    args = parser.parse_args()

    # Initialize populator
    populator = PriceHistoryPopulator()

    # Get snapshots needing prices
    snapshots = populator.get_snapshots_needing_prices(ticker=args.ticker, limit=args.limit)

    if not snapshots:
        logger.info('No snapshots need price_history population!')
        return 0

    logger.info(f'Found {len(snapshots)} snapshots needing price_history')

    # Group by ticker for logging
    tickers = list({s['ticker'] for s in snapshots})
    logger.info(f'Covering {len(tickers)} unique tickers')

    # Process each snapshot
    success_count = 0
    fail_count = 0

    for i, snapshot in enumerate(snapshots, 1):
        logger.info(f'Processing {i}/{len(snapshots)}: {snapshot["ticker"]} on {snapshot["snapshot_date"]}')

        success = populator.fetch_and_save_price_history(
            snapshot['snapshot_id'],
            snapshot['ticker'],
            snapshot['snapshot_date']
        )

        if success:
            success_count += 1
        else:
            fail_count += 1

        # Progress update every 10 stocks
        if i % 10 == 0:
            logger.info(f'Progress: {i}/{len(snapshots)} snapshots - {success_count} succeeded, {fail_count} failed')

    # Final summary
    logger.info(f'''
Price history population complete:
  - Total snapshots: {len(snapshots)}
  - Successful: {success_count}
  - Failed: {fail_count}
  - Success rate: {success_count/len(snapshots)*100:.1f}%
''')

    return 0


if __name__ == '__main__':
    sys.exit(main())
