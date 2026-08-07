"""
Historical fundamental data provider for GBM backtesting.
Provides point-in-time fundamental data from the fundamental_history table.
"""

import logging
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class FundamentalHistoryProvider:
    """
    Provides historical fundamental data for GBM backtesting.
    Ensures no look-ahead bias by using only data available at each point in time.
    """

    def __init__(self, db_path: Optional[str] = None):
        """Initialize fundamental history provider with database path."""
        if db_path is None:
            # Default to main database
            db_path = Path(__file__).parent.parent.parent / 'data' / 'stock_data.db'

        self.db_path = str(db_path)
        logger.info(f'Initialized FundamentalHistoryProvider with database: {self.db_path}')

    def get_snapshots_as_of(self, date: pd.Timestamp,
                           min_snapshots: int = 12) -> pd.DataFrame:
        """
        Get most recent snapshots available as of a specific date.

        For backtesting, we need to simulate what data would have been available
        at that point in time. We use a 60-day lag to account for filing delays.

        Parameters
        ----------
        date : pd.Timestamp
            The "as of" date for backtesting
        min_snapshots : int
            Minimum number of historical snapshots required (default 12 for full GBM)

        Returns
        -------
        pd.DataFrame
            DataFrame with columns matching snapshots table schema
            Index: ticker symbols
        """
        # Add 60-day lag to account for filing delays (10-Q/10-K filings)
        # A quarter ending March 31 won't be filed until ~May 10 (40 days)
        # We use 60 days to be conservative
        filing_lag_date = date - timedelta(days=60)

        logger.info(f'Getting snapshots as of {date} (filing lag: {filing_lag_date})')

        conn = sqlite3.connect(self.db_path)

        try:
            # Get most recent snapshot per stock before filing_lag_date
            query = f"""
            WITH ranked_snapshots AS (
                SELECT
                    s.*,
                    a.symbol,
                    a.sector,
                    ROW_NUMBER() OVER (
                        PARTITION BY s.asset_id
                        ORDER BY s.snapshot_date DESC
                    ) as rn,
                    COUNT(*) OVER (PARTITION BY s.asset_id) as total_snapshots
                FROM snapshots s
                JOIN assets a ON s.asset_id = a.id
                WHERE s.snapshot_date <= '{filing_lag_date.strftime('%Y-%m-%d')}'
            )
            SELECT * FROM ranked_snapshots
            WHERE rn = 1 AND total_snapshots >= {min_snapshots}
            """

            df = pd.read_sql_query(query, conn)

            if len(df) == 0:
                logger.warning(f'No snapshots found as of {date}')
                return pd.DataFrame()

            # Set ticker as index
            df = df.set_index('symbol')

            logger.info(f'Loaded {len(df)} snapshots (min {min_snapshots} history required)')

            return df

        finally:
            conn.close()

    def get_historical_snapshots(self, ticker: str,
                                as_of_date: pd.Timestamp,
                                lookback_quarters: int = 12) -> pd.DataFrame:
        """
        Get historical snapshots for a single ticker.

        Used for feature engineering (lags, rolling windows).

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        as_of_date : pd.Timestamp
            The "as of" date (with 60-day filing lag already applied)
        lookback_quarters : int
            Number of quarters of history to retrieve

        Returns
        -------
        pd.DataFrame
            Historical snapshots sorted by date (oldest first)
        """
        filing_lag_date = as_of_date - timedelta(days=60)

        conn = sqlite3.connect(self.db_path)

        try:
            query = f"""
            SELECT s.*, a.sector
            FROM snapshots s
            JOIN assets a ON s.asset_id = a.id
            WHERE a.symbol = '{ticker}'
              AND s.snapshot_date <= '{filing_lag_date.strftime('%Y-%m-%d')}'
            ORDER BY s.snapshot_date DESC
            LIMIT {lookback_quarters}
            """

            df = pd.read_sql_query(query, conn)

            # Reverse to get chronological order (oldest first)
            df = df.sort_values('snapshot_date').reset_index(drop=True)

            return df

        finally:
            conn.close()

    def get_price_data(self, ticker: str,
                      as_of_date: pd.Timestamp,
                      lookback_days: int = 365) -> pd.DataFrame:
        """
        Get historical price data for momentum feature calculation.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        as_of_date : pd.Timestamp
            The "as of" date
        lookback_days : int
            Number of days of price history

        Returns
        -------
        pd.DataFrame
            Price history with columns: date, close, volume
        """
        start_date = as_of_date - timedelta(days=lookback_days)

        conn = sqlite3.connect(self.db_path)

        try:
            query = f"""
            SELECT date, close, volume
            FROM price_history
            WHERE ticker = '{ticker}'
              AND date >= '{start_date.strftime('%Y-%m-%d')}'
              AND date <= '{as_of_date.strftime('%Y-%m-%d')}'
            ORDER BY date
            """

            df = pd.read_sql_query(query, conn)
            df['date'] = pd.to_datetime(df['date'])

            return df

        finally:
            conn.close()

    def compute_price_features(self, price_df: pd.DataFrame) -> Dict[str, float]:
        """
        Compute price-based momentum features.

        Parameters
        ----------
        price_df : pd.DataFrame
            Price history with 'close' and 'volume' columns

        Returns
        -------
        Dict[str, float]
            Dictionary with price features: returns_1m, returns_3m, etc.
        """
        if len(price_df) < 20:
            # Not enough data
            return {
                'returns_1m': 0.0,
                'returns_3m': 0.0,
                'returns_6m': 0.0,
                'returns_1y': 0.0,
                'volatility': 0.0,
                'volume_trend': 0.0,
            }

        prices = price_df['close'].values
        volumes = price_df['volume'].values

        # Calculate returns
        current_price = prices[-1]

        # 1-month return (21 trading days)
        returns_1m = (current_price / prices[-22] - 1) if len(prices) >= 22 else 0.0

        # 3-month return (63 trading days)
        returns_3m = (current_price / prices[-64] - 1) if len(prices) >= 64 else 0.0

        # 6-month return (126 trading days)
        returns_6m = (current_price / prices[-127] - 1) if len(prices) >= 127 else 0.0

        # 1-year return (252 trading days)
        returns_1y = (current_price / prices[-253] - 1) if len(prices) >= 253 else 0.0

        # Volatility (60-day standard deviation of daily returns)
        daily_returns = np.diff(prices[-61:]) / prices[-61:-1]
        volatility = np.std(daily_returns) if len(daily_returns) > 0 else 0.0

        # Volume trend (recent vs average)
        recent_volume = np.mean(volumes[-20:]) if len(volumes) >= 20 else volumes[-1]
        avg_volume = np.mean(volumes) if len(volumes) > 0 else 1.0
        volume_trend = (recent_volume / avg_volume - 1) if avg_volume > 0 else 0.0

        return {
            'returns_1m': returns_1m,
            'returns_3m': returns_3m,
            'returns_6m': returns_6m,
            'returns_1y': returns_1y,
            'volatility': volatility,
            'volume_trend': volume_trend,
        }

    def get_available_tickers_as_of(self, date: pd.Timestamp,
                                   min_snapshots: int = 12) -> List[str]:
        """
        Get list of tickers with sufficient history as of a date.

        Parameters
        ----------
        date : pd.Timestamp
            The "as of" date
        min_snapshots : int
            Minimum number of historical snapshots required

        Returns
        -------
        List[str]
            List of ticker symbols
        """
        filing_lag_date = date - timedelta(days=60)

        conn = sqlite3.connect(self.db_path)

        try:
            query = f"""
            SELECT a.symbol, COUNT(*) as snapshot_count
            FROM snapshots s
            JOIN assets a ON s.asset_id = a.id
            WHERE s.snapshot_date <= '{filing_lag_date.strftime('%Y-%m-%d')}'
            GROUP BY a.symbol
            HAVING snapshot_count >= {min_snapshots}
            ORDER BY a.symbol
            """

            df = pd.read_sql_query(query, conn)

            return df['symbol'].tolist()

        finally:
            conn.close()
