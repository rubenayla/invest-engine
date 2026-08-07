#!/usr/bin/env python3
'''
Calculate historical PE and PB ratios for snapshots using price_history data.

This script:
- Finds snapshots missing pe_ratio and pb_ratio
- Gets historical price from price_history for each snapshot date
- Fetches shares outstanding from yfinance (current value used as approximation)
- Calculates EPS = net_income / shares_outstanding (if data available)
- Calculates book_value_per_share = total_equity / shares_outstanding
- Calculates pe_ratio = price / EPS
- Calculates pb_ratio = price / book_value_per_share
'''

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Optional

import yfinance as yf

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HistoricalRatioCalculator:
    '''Calculates PE and PB ratios for historical snapshots.'''

    def __init__(self, db_path: str = 'data/stock_data.db'):
        self.db_path = Path(project_root) / db_path
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.shares_cache = {}  # Cache shares outstanding per ticker

    def get_shares_outstanding(self, ticker: str) -> Optional[float]:
        '''Get shares outstanding from yfinance (cached).'''
        if ticker in self.shares_cache:
            return self.shares_cache[ticker]

        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            shares = info.get('sharesOutstanding')

            if shares and shares > 0:
                self.shares_cache[ticker] = float(shares)
                return float(shares)
            else:
                logger.warning(f'{ticker}: No shares outstanding data')
                return None

        except Exception as e:
            logger.warning(f'{ticker}: Error fetching shares - {e}')
            return None

    def get_avg_price_for_snapshot(self, snapshot_id: int) -> Optional[float]:
        '''Get average price from price_history for a snapshot.'''
        query = '''
            SELECT AVG(close) as avg_price
            FROM price_history
            WHERE snapshot_id = ?
        '''
        result = self.cursor.execute(query, (snapshot_id,)).fetchone()

        if result and result[0]:
            return float(result[0])
        return None

    def calculate_and_update_ratios(self, snapshot_id: int, ticker: str,
                                   net_income: float, total_equity: float,
                                   avg_price: float, shares: float) -> bool:
        '''Calculate PE and PB ratios and update snapshot.'''
        try:
            # Calculate EPS and book value per share
            if shares <= 0:
                return False

            eps = net_income / shares if net_income else None
            book_value_per_share = total_equity / shares if total_equity else None

            # Calculate ratios
            pe_ratio = avg_price / eps if eps and eps > 0 else None
            pb_ratio = avg_price / book_value_per_share if book_value_per_share and book_value_per_share > 0 else None

            # Update snapshot
            updates = []
            params = []

            if pe_ratio is not None and -100 < pe_ratio < 1000:  # Sanity check
                updates.append('pe_ratio = ?')
                params.append(pe_ratio)

            if pb_ratio is not None and -10 < pb_ratio < 100:  # Sanity check
                updates.append('pb_ratio = ?')
                params.append(pb_ratio)

            if eps is not None:
                updates.append('trailing_eps = ?')
                params.append(eps)

            if book_value_per_share is not None:
                updates.append('book_value = ?')
                params.append(book_value_per_share)

            if shares is not None:
                updates.append('shares_outstanding = ?')
                params.append(shares)

            if updates:
                params.append(snapshot_id)
                query = f'UPDATE fundamental_history SET {", ".join(updates)} WHERE id = ?'
                self.cursor.execute(query, params)
                self.conn.commit()
                return True

            return False

        except Exception as e:
            logger.warning(f'{ticker} (snapshot {snapshot_id}): Error calculating ratios - {e}')
            return False

    def process_all_snapshots(self):
        '''Process all snapshots missing PE/PB ratios.'''
        # Get snapshots missing ratios but having EPS and book value
        query = '''
            SELECT
                s.id,
                a.symbol,
                s.snapshot_date,
                s.trailing_eps,
                s.book_value
            FROM fundamental_history s
            JOIN assets a ON s.asset_id = a.id
            WHERE (s.pe_ratio IS NULL OR s.pb_ratio IS NULL)
                AND s.trailing_eps IS NOT NULL
                AND s.book_value IS NOT NULL
            ORDER BY a.symbol, s.snapshot_date
        '''

        snapshots = self.cursor.execute(query).fetchall()
        logger.info(f'Found {len(snapshots)} snapshots missing ratios')

        if not snapshots:
            logger.info('All snapshots already have ratios!')
            return 0

        # Process snapshots
        updated_count = 0
        failed_count = 0

        for i, (snapshot_id, ticker, snapshot_date, trailing_eps, book_value) in enumerate(snapshots):
            # Get historical price
            avg_price = self.get_avg_price_for_snapshot(snapshot_id)

            if avg_price is None:
                logger.debug(f'{ticker} ({snapshot_date}): No price history')
                failed_count += 1
                continue

            # Calculate PE and PB ratios
            try:
                pe_ratio = None
                pb_ratio = None

                if trailing_eps and trailing_eps > 0:
                    pe_ratio = avg_price / trailing_eps
                    # Sanity check
                    if pe_ratio < -100 or pe_ratio > 1000:
                        pe_ratio = None

                if book_value and book_value > 0:
                    pb_ratio = avg_price / book_value
                    # Sanity check
                    if pb_ratio < -10 or pb_ratio > 100:
                        pb_ratio = None

                # Update snapshot
                updates = []
                params = []

                if pe_ratio is not None:
                    updates.append('pe_ratio = ?')
                    params.append(pe_ratio)

                if pb_ratio is not None:
                    updates.append('pb_ratio = ?')
                    params.append(pb_ratio)

                if updates:
                    params.append(snapshot_id)
                    query_update = f'UPDATE fundamental_history SET {", ".join(updates)} WHERE id = ?'
                    self.cursor.execute(query_update, params)
                    self.conn.commit()
                    updated_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                logger.warning(f'{ticker} ({snapshot_date}): Error calculating ratios - {e}')
                failed_count += 1

            # Progress update
            if (i + 1) % 100 == 0:
                logger.info(f'Progress: {i+1}/{len(snapshots)} - Updated: {updated_count}, Failed: {failed_count}')

        return updated_count

    def close(self):
        '''Close database connection.'''
        self.conn.close()


def main():
    '''Main execution function.'''
    logger.info('=' * 60)
    logger.info('Calculating Historical PE/PB Ratios')
    logger.info('=' * 60)

    calculator = HistoricalRatioCalculator()

    updated_count = calculator.process_all_snapshots()

    logger.info('\\n' + '=' * 60)
    logger.info('Historical Ratio Calculation Complete!')
    logger.info('=' * 60)
    logger.info(f'Updated snapshots: {updated_count}')
    logger.info('=' * 60)

    calculator.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
