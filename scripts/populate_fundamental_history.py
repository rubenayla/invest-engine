#!/usr/bin/env python3
"""
Populate historical snapshots for stocks missing temporal data.

This script fetches historical fundamental data from yfinance at 6-month intervals
and populates the assets/snapshots tables so neural networks can make predictions.
"""

import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / 'src'))

from invest.data.db import get_connection

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class HistoricalSnapshotFetcher:
    """Fetches historical fundamental data and populates snapshots table."""

    def __init__(self, db_path: str = None):
        self.conn = get_connection()
        self.cursor = self.conn.cursor()

        # Rate limiting
        self.request_count = 0
        self.last_request_time = time.time()
        self.requests_per_minute = 30  # Conservative limit

        # VIX cache (date -> VIX value)
        self.vix_cache = {}
        self._fetch_vix_history()

    def get_stocks_without_snapshots(self) -> List[tuple]:
        """Get list of stocks that don't have historical snapshots."""
        query = '''
        SELECT ticker, current_price, sector, industry
        FROM current_stock_data
        WHERE ticker NOT IN (SELECT DISTINCT symbol FROM assets)
        ORDER BY ticker
        '''
        self.cursor.execute(query)
        return self.cursor.fetchall()

    def get_or_create_asset(self, ticker: str, sector: str = None, industry: str = None) -> int:
        """Get asset_id or create new asset entry."""
        # Check if asset exists
        self.cursor.execute(
            'SELECT id FROM assets WHERE symbol = %s',
            (ticker,)
        )
        result = self.cursor.fetchone()

        if result:
            return result[0]

        # Create new asset
        self.cursor.execute('''
            INSERT INTO assets (symbol, asset_type, sector, industry)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        ''', (ticker, 'stock', sector or 'Unknown', industry or 'Unknown'))

        asset_id = self.cursor.fetchone()[0]
        self.conn.commit()
        return asset_id

    def rate_limit(self):
        """Simple rate limiting to avoid overwhelming yfinance."""
        self.request_count += 1

        # Every 30 requests, wait a bit
        if self.request_count % self.requests_per_minute == 0:
            elapsed = time.time() - self.last_request_time
            if elapsed < 60:
                wait_time = 60 - elapsed
                logger.info(f'Rate limiting: waiting {wait_time:.1f}s...')
                time.sleep(wait_time)
            self.last_request_time = time.time()

    def _fetch_vix_history(self):
        """Fetch VIX historical data and cache it."""
        try:
            logger.info('Fetching VIX historical data...')
            vix = yf.Ticker('^VIX')

            # Fetch VIX history from 2000 to today
            hist = vix.history(start='2000-01-01', end=datetime.now().strftime('%Y-%m-%d'))

            if hist.empty:
                logger.warning('No VIX data retrieved, will use default value')
                return

            # Cache VIX close price by date
            for date, row in hist.iterrows():
                date_str = date.strftime('%Y-%m-%d')
                self.vix_cache[date_str] = float(row['Close'])

            logger.info(f'Cached VIX data for {len(self.vix_cache)} dates')

        except Exception as e:
            logger.warning(f'Error fetching VIX history: {e}. Will use default value.')

    def get_vix_for_date(self, date_str: str) -> Optional[float]:
        """Get VIX value for a specific date, or None if not available."""
        # Direct match
        if date_str in self.vix_cache:
            return self.vix_cache[date_str]

        # Try to find closest previous trading day (within 7 days)
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        for days_back in range(1, 8):
            check_date = (target_date - timedelta(days=days_back)).strftime('%Y-%m-%d')
            if check_date in self.vix_cache:
                return self.vix_cache[check_date]

        # Default fallback
        return 20.0  # Historical median

    def fetch_historical_snapshots(self, ticker: str) -> List[Dict]:
        """
        Fetch historical fundamental data from quarterly statements + current info.

        Creates snapshots from quarterly financial statements (historical) and
        enriches the latest snapshot with current stock.info data (ratios, market
        data, etc.) that yfinance only provides for the current period.
        """
        self.rate_limit()

        try:
            stock = yf.Ticker(ticker)

            # Get current info (has ratios, market data, etc.)
            try:
                info = stock.info or {}
            except Exception as e:
                logger.warning(f'{ticker}: Could not fetch info - {e}')
                info = {}

            sector = info.get('sector', 'Unknown')

            # Get quarterly data
            snapshots = []
            try:
                quarterly_financials = stock.quarterly_financials
                quarterly_balance_sheet = stock.quarterly_balance_sheet
                quarterly_cashflow = stock.quarterly_cashflow

                if quarterly_financials is not None and not quarterly_financials.empty:
                    available_dates = quarterly_financials.columns

                    for date in available_dates:
                        snapshot = self._extract_snapshot_from_quarterly(
                            ticker=ticker,
                            snapshot_date=date,
                            financials=quarterly_financials,
                            balance_sheet=quarterly_balance_sheet,
                            cashflow=quarterly_cashflow,
                            sector=sector,
                        )
                        if snapshot:
                            snapshots.append(snapshot)

                    logger.info(f'{ticker}: Created {len(snapshots)} snapshots from quarterly data')
                else:
                    logger.warning(f'{ticker}: No quarterly financials available')

            except Exception as e:
                logger.warning(f'{ticker}: Error fetching quarterly data - {e}')

            # Enrich the latest snapshot (or create one) with stock.info data
            if info.get('currentPrice'):
                self._enrich_latest_snapshot(snapshots, info, ticker)

            return snapshots

        except Exception as e:
            logger.error(f'{ticker}: Failed to fetch data - {e}')
            return []

    def _enrich_latest_snapshot(self, snapshots: List[Dict], info: Dict, ticker: str):
        """Enrich the latest snapshot with current stock.info data."""
        # Map yfinance info keys -> fundamental_history column names
        INFO_MAP = {
            'marketCap': 'market_cap',
            'trailingPE': 'pe_ratio',
            'priceToBook': 'pb_ratio',
            'priceToSalesTrailing12Months': 'ps_ratio',
            'pegRatio': 'peg_ratio',
            'enterpriseToRevenue': 'enterprise_to_revenue',
            'enterpriseToEbitda': 'enterprise_to_ebitda',
            'profitMargins': 'profit_margins',
            'operatingMargins': 'operating_margins',
            'grossMargins': 'gross_margins',
            'ebitdaMargins': 'ebitda_margins',
            'returnOnAssets': 'return_on_assets',
            'returnOnEquity': 'return_on_equity',
            'revenueGrowth': 'revenue_growth',
            'earningsGrowth': 'earnings_growth',
            'earningsQuarterlyGrowth': 'earnings_quarterly_growth',
            'revenuePerShare': 'revenue_per_share',
            'totalCash': 'total_cash',
            'totalDebt': 'total_debt',
            'debtToEquity': 'debt_to_equity',
            'currentRatio': 'current_ratio',
            'quickRatio': 'quick_ratio',
            'operatingCashflow': 'operating_cashflow',
            'freeCashflow': 'free_cashflow',
            'trailingEps': 'trailing_eps',
            'forwardEps': 'forward_eps',
            'bookValue': 'book_value',
            'dividendRate': 'dividend_rate',
            'dividendYield': 'dividend_yield',
            'payoutRatio': 'payout_ratio',
            'beta': 'beta',
            'fiftyDayAverage': 'fifty_day_average',
            'twoHundredDayAverage': 'two_hundred_day_average',
            'fiftyTwoWeekHigh': 'fifty_two_week_high',
            'fiftyTwoWeekLow': 'fifty_two_week_low',
            'volume': 'volume',
            'sharesOutstanding': 'shares_outstanding',
        }

        # Duplicate mappings: same yfinance field -> multiple DB columns
        DUPLICATE_MAP = {
            'pb_ratio': 'price_to_book',
            'ps_ratio': 'price_to_sales',
        }

        # Convert debtToEquity from percentage to ratio if needed
        dte = info.get('debtToEquity')
        if dte is not None and dte > 10:
            info['debtToEquity'] = dte / 100.0

        enrichment = {}
        for info_key, col_name in INFO_MAP.items():
            val = info.get(info_key)
            if val is not None and isinstance(val, (int, float)):
                enrichment[col_name] = float(val)

        # Copy duplicate mappings (same value -> multiple columns)
        for src, dst in DUPLICATE_MAP.items():
            if src in enrichment:
                enrichment[dst] = enrichment[src]

        if not enrichment:
            return

        if snapshots:
            # Enrich the latest (most recent date) snapshot
            snapshots.sort(key=lambda s: s['snapshot_date'], reverse=True)
            for key, val in enrichment.items():
                # Only fill if missing
                if snapshots[0].get(key) is None:
                    snapshots[0][key] = val
        else:
            # No quarterly data at all — create a snapshot from info alone
            today = datetime.now().strftime('%Y-%m-%d')
            snapshot = {
                'ticker': ticker,
                'snapshot_date': today,
                'vix': self.get_vix_for_date(today),
                **enrichment,
            }
            snapshots.append(snapshot)

    def _extract_snapshot_from_quarterly(
        self,
        ticker: str,
        snapshot_date: pd.Timestamp,
        financials: pd.DataFrame,
        balance_sheet: pd.DataFrame,
        cashflow: pd.DataFrame,
        sector: str,
    ) -> Optional[Dict]:
        """Extract snapshot data from quarterly financials."""
        try:
            date_str = snapshot_date.strftime('%Y-%m-%d')

            snapshot = {
                'ticker': ticker,
                'snapshot_date': date_str,
                'sector': sector,
                'vix': self.get_vix_for_date(date_str),
            }

            # From financials (income statement)
            if financials is not None and snapshot_date in financials.columns:
                fin = financials[snapshot_date]
                snapshot['total_revenue'] = self._safe_float(fin.get('Total Revenue'))
                snapshot['operating_income'] = self._safe_float(fin.get('Operating Income'))
                snapshot['net_income'] = self._safe_float(fin.get('Net Income'))
                snapshot['ebitda'] = self._safe_float(fin.get('EBITDA'))

            # From balance sheet
            if balance_sheet is not None and snapshot_date in balance_sheet.columns:
                bs = balance_sheet[snapshot_date]
                snapshot['total_assets'] = self._safe_float(bs.get('Total Assets'))
                snapshot['total_debt'] = self._safe_float(bs.get('Total Debt'))
                snapshot['total_equity'] = self._safe_float(bs.get('Stockholders Equity'))
                snapshot['total_cash'] = self._safe_float(bs.get('Cash And Cash Equivalents'))
                snapshot['current_assets'] = self._safe_float(bs.get('Current Assets'))
                snapshot['current_liabilities'] = self._safe_float(bs.get('Current Liabilities'))

            # From cashflow
            if cashflow is not None and snapshot_date in cashflow.columns:
                cf = cashflow[snapshot_date]
                snapshot['operating_cashflow'] = self._safe_float(cf.get('Operating Cash Flow'))
                snapshot['free_cashflow'] = self._safe_float(cf.get('Free Cash Flow'))

            # Calculate derived metrics
            rev = snapshot.get('total_revenue')
            ni = snapshot.get('net_income')
            oi = snapshot.get('operating_income')
            eq = snapshot.get('total_equity')
            td = snapshot.get('total_debt')
            ca = snapshot.get('current_assets')
            cl = snapshot.get('current_liabilities')

            if rev and ni:
                snapshot['profit_margins'] = ni / rev
            if rev and oi:
                snapshot['operating_margins'] = oi / rev
            if rev and snapshot.get('ebitda'):
                snapshot['ebitda_margins'] = snapshot['ebitda'] / rev
            if ni and eq and eq != 0:
                snapshot['return_on_equity'] = ni / eq
            if ni and snapshot.get('total_assets') and snapshot['total_assets'] != 0:
                snapshot['return_on_assets'] = ni / snapshot['total_assets']
            if td is not None and eq and eq != 0:
                snapshot['debt_to_equity'] = td / eq
            if ca and cl and cl != 0:
                snapshot['current_ratio'] = ca / cl

            return snapshot

        except Exception as e:
            logger.warning(f'{ticker} ({snapshot_date}): Error extracting snapshot - {e}')
            return None

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """Safely convert a value to float, returning None on failure."""
        if val is None:
            return None
        try:
            import math
            f = float(val)
            return f if not math.isnan(f) else None
        except (ValueError, TypeError):
            return None

    # All columns in fundamental_history that we populate
    SNAPSHOT_COLUMNS = [
        'asset_id', 'snapshot_date',
        'volume', 'market_cap', 'shares_outstanding',
        'pe_ratio', 'pb_ratio', 'ps_ratio', 'peg_ratio',
        'price_to_book', 'price_to_sales',
        'enterprise_to_revenue', 'enterprise_to_ebitda',
        'profit_margins', 'operating_margins', 'gross_margins', 'ebitda_margins',
        'return_on_assets', 'return_on_equity',
        'revenue_growth', 'earnings_growth', 'earnings_quarterly_growth',
        'revenue_per_share',
        'total_cash', 'total_debt', 'debt_to_equity',
        'current_ratio', 'quick_ratio',
        'operating_cashflow', 'free_cashflow',
        'trailing_eps', 'forward_eps', 'book_value',
        'dividend_rate', 'dividend_yield', 'payout_ratio',
        'beta',
        'fifty_day_average', 'two_hundred_day_average',
        'fifty_two_week_high', 'fifty_two_week_low',
        'vix',
    ]

    def save_snapshots(self, asset_id: int, snapshots: List[Dict]):
        """Save snapshots to database, inserting all available columns."""
        cols = self.SNAPSHOT_COLUMNS
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)

        for snapshot in snapshots:
            try:
                values = [asset_id, snapshot['snapshot_date']]
                # Fill remaining columns from snapshot dict (skip asset_id, snapshot_date)
                for col in cols[2:]:
                    values.append(snapshot.get(col))

                self.cursor.execute(
                    f'INSERT INTO fundamental_history ({col_names}) VALUES ({placeholders}) ON CONFLICT DO NOTHING',
                    values,
                )
            except Exception as e:
                self.conn.rollback()
                logger.warning(f'Error saving snapshot: {e}')

        self.conn.commit()

    def process_stock(self, ticker: str, sector: str = None, industry: str = None) -> int:
        """Process a single stock and return number of snapshots created."""
        logger.info(f'{ticker}: Fetching historical snapshots...')

        # Get or create asset
        asset_id = self.get_or_create_asset(ticker, sector, industry)

        # Fetch snapshots
        snapshots = self.fetch_historical_snapshots(ticker)

        if snapshots:
            self.save_snapshots(asset_id, snapshots)
            logger.info(f'{ticker}: Saved {len(snapshots)} snapshots')
            return len(snapshots)
        else:
            logger.warning(f'{ticker}: No snapshots created')
            return 0

    def close(self):
        """Close database connection."""
        self.conn.close()


def main():
    """Main execution function."""
    import argparse

    parser = argparse.ArgumentParser(description='Populate historical fundamental snapshots')
    parser.add_argument('--refresh', action='store_true',
                        help='Re-fetch tickers that have sparse/empty data (not just missing ones)')
    parser.add_argument('--tickers', type=str, default=None,
                        help='Comma-separated list of specific tickers to process')
    args = parser.parse_args()

    logger.info('=' * 60)
    logger.info('Populating Historical Snapshots')
    logger.info('=' * 60)

    fetcher = HistoricalSnapshotFetcher()

    if args.tickers:
        # Process specific tickers
        ticker_list = [t.strip().upper() for t in args.tickers.split(',')]
        stocks = []
        for t in ticker_list:
            fetcher.cursor.execute(
                'SELECT ticker, current_price, sector, industry FROM current_stock_data WHERE ticker = %s',
                (t,)
            )
            row = fetcher.cursor.fetchone()
            if row:
                stocks.append(row)
            else:
                logger.warning(f'{t}: Not found in current_stock_data')
    elif args.refresh:
        # Get tickers with sparse data (few non-null fields in latest snapshot)
        fetcher.cursor.execute('''
            SELECT c.ticker, c.current_price, c.sector, c.industry
            FROM current_stock_data c
            WHERE c.current_price IS NOT NULL
            AND (
                -- Not in assets at all
                c.ticker NOT IN (SELECT DISTINCT symbol FROM assets)
                OR
                -- In assets but latest snapshot has mostly nulls
                c.ticker IN (
                    SELECT a.symbol FROM assets a
                    JOIN fundamental_history f ON f.asset_id = a.id
                    GROUP BY a.symbol
                    HAVING SUM(CASE WHEN f.pe_ratio IS NOT NULL
                                      OR f.trailing_eps IS NOT NULL
                                      OR f.market_cap IS NOT NULL
                               THEN 1 ELSE 0 END) = 0
                )
            )
            ORDER BY c.ticker
        ''')
        stocks = fetcher.cursor.fetchall()
    else:
        stocks = fetcher.get_stocks_without_snapshots()

    logger.info(f'Found {len(stocks)} stocks to process')

    if not stocks:
        logger.info('Nothing to do!')
        fetcher.close()
        return 0

    # For --refresh, delete existing empty snapshots before re-fetching
    if args.refresh:
        for (ticker, *_) in stocks:
            fetcher.cursor.execute(
                'SELECT id FROM assets WHERE symbol = %s', (ticker,)
            )
            asset = fetcher.cursor.fetchone()
            if asset:
                fetcher.cursor.execute(
                    'DELETE FROM fundamental_history WHERE asset_id = %s', (asset[0],)
                )
        fetcher.conn.commit()
        logger.info(f'Cleared existing empty snapshots for {len(stocks)} tickers')

    total_snapshots = 0
    successful_stocks = 0
    failed_stocks = 0

    for i, (ticker, price, sector, industry) in enumerate(stocks, 1):
        try:
            logger.info(f'[{i}/{len(stocks)}] Processing {ticker}...')
            count = fetcher.process_stock(ticker, sector, industry)

            if count > 0:
                total_snapshots += count
                successful_stocks += 1
            else:
                failed_stocks += 1

            if i % 10 == 0:
                logger.info(f'Progress: {i}/{len(stocks)} | OK: {successful_stocks} | Fail: {failed_stocks} | Snapshots: {total_snapshots}')

        except Exception as e:
            logger.error(f'{ticker}: Unexpected error - {e}')
            failed_stocks += 1

    logger.info('=' * 60)
    logger.info(f'Done! Processed: {len(stocks)} | OK: {successful_stocks} | Failed: {failed_stocks} | Snapshots: {total_snapshots}')
    logger.info('=' * 60)

    fetcher.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
