"""
Historical data provider for backtesting with no look-ahead bias.
"""

import logging
import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class HistoricalDataProvider:
    """
    Provides historical data for backtesting.
    Ensures no look-ahead bias by only using data available at each point in time.
    Uses database for price history instead of fetching from yfinance.
    """

    def __init__(self, cache_dir: Optional[str] = None, db_path: Optional[str] = None) -> None:
        """Initialize data provider with optional cache directory and database path."""
        self.cache_dir = cache_dir
        self._price_cache: Dict[str, pd.DataFrame] = {}
        self._fundamental_cache: Dict[str, Dict[str, Any]] = {}

        # Database path for price history
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / 'data' / 'stock_data.db'
        self.db_path = str(db_path)

        logger.info(f'Initialized HistoricalDataProvider with database: {self.db_path}')

    def get_data_as_of(self, date: pd.Timestamp, tickers: List[str],
                        lookback_days: int = 365) -> Dict[str, Any]:
        """
        Get all data available as of a specific date (point-in-time).

        Parameters
        ----------
        date : pd.Timestamp
            The "as of" date - only data before this date is used
        tickers : List[str]
            List of tickers to get data for
        lookback_days : int
            Number of days of history to include

        Returns
        -------
        Dict[str, Any]
            Dictionary containing:
            - current_prices: Dict of ticker -> price as of date
            - price_history: DataFrame of historical prices
            - fundamentals: Dict of ticker -> fundamental data
            - financial_metrics: Dict of ticker -> metrics for screening
        """
        logger.info(f'Getting point-in-time data as of {date}')

        # Calculate lookback period
        start_date = date - timedelta(days=lookback_days)

        # --- Survivorship-bias filter: drop delisted tickers --------------
        available = self.get_available_tickers_as_of(date, tickers)
        dropped = set(tickers) - available
        if dropped:
            for t in sorted(dropped):
                logger.warning(
                    'Ticker %s dropped from universe as of %s '
                    '(no recent price data — likely delisted)', t, date
                )
        active_tickers = [t for t in tickers if t in available]
        # ------------------------------------------------------------------

        # Get price data
        price_history = self._get_price_history_range(
            active_tickers, start_date, date
        )

        # Get current prices (last available price before or on date)
        current_prices = {}
        for ticker in active_tickers:
            if ticker in price_history.columns:
                ticker_prices = price_history[ticker].dropna()
                if len(ticker_prices) > 0:
                    current_prices[ticker] = ticker_prices.iloc[-1]

        # Get fundamental data (as it would have been available at that date)
        fundamentals = self._get_fundamentals_as_of(active_tickers, date)

        # Calculate financial metrics for screening
        financial_metrics = self._calculate_metrics_as_of(
            active_tickers, price_history, fundamentals, date
        )

        return {
            'date': date,
            'current_prices': current_prices,
            'price_history': price_history,
            'fundamentals': fundamentals,
            'financial_metrics': financial_metrics,
            'dropped_tickers': dropped,
        }

    def get_prices(self, tickers: List[str], date: pd.Timestamp) -> Dict[str, float]:
        """Get prices for specific tickers on a specific date from the database."""
        prices: Dict[str, float] = {}

        for ticker in tickers:
            price = self._get_single_price(ticker, date)
            if price is not None:
                prices[ticker] = price

        return prices

    def get_price_history(self, ticker: str, start_date: pd.Timestamp,
                          end_date: pd.Timestamp) -> pd.DataFrame:
        """Get price history for a single ticker from database."""
        cache_key = f"{ticker}_{start_date}_{end_date}"

        if cache_key not in self._price_cache:
            try:
                conn = sqlite3.connect(self.db_path)
                query = '''
                SELECT date, open, high, low, close, volume
                FROM price_history
                WHERE ticker = ?
                AND date >= ?
                AND date <= ?
                ORDER BY date
                '''
                df = pd.read_sql(
                    query,
                    conn,
                    params=(ticker, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')),
                    parse_dates=['date'],
                    index_col='date'
                )
                conn.close()

                # Rename columns to match yfinance format
                if not df.empty:
                    df.columns = ['Open', 'High', 'Low', 'Close', 'Volume']

                self._price_cache[cache_key] = df
            except Exception as e:
                logger.error(f"Error fetching {ticker} from database: {e}")
                self._price_cache[cache_key] = pd.DataFrame()

        return self._price_cache[cache_key]

    def _get_price_history_range(self, tickers: List[str],
                                  start_date: pd.Timestamp,
                                  end_date: pd.Timestamp) -> pd.DataFrame:
        """Get price history for multiple tickers."""
        price_series = []

        for ticker in tickers:
            history = self.get_price_history(ticker, start_date, end_date)
            if not history.empty and 'Close' in history.columns:
                series = history['Close'].copy()
                series.name = ticker
                price_series.append(series)

        if price_series:
            # Combine all series into a DataFrame
            return pd.concat(price_series, axis=1)
        else:
            return pd.DataFrame()

    def _get_fundamentals_as_of(self, tickers: List[str],
                                 date: pd.Timestamp) -> Dict[str, Dict]:
        """
        Get fundamental data as it would have been available at a point in time.

        Uses the fundamental_history table (point-in-time snapshots) instead of
        yfinance's current data to avoid look-ahead bias. Applies a reporting
        lag of 45 days (companies don't publish financials on period-end date).
        """
        fundamentals = {}
        reporting_lag_days = 45  # Conservative lag for financial reporting

        try:
            conn = sqlite3.connect(self.db_path)

            # Pre-fetch asset metadata (sector, industry) — these are stable
            asset_meta = {}
            meta_query = 'SELECT id, symbol, sector, industry FROM assets'
            for row in conn.execute(meta_query).fetchall():
                asset_meta[row[1]] = {'id': row[0], 'sector': row[2], 'industry': row[3]}

            for ticker in tickers:
                meta = asset_meta.get(ticker, {})
                asset_id = meta.get('id')

                if asset_id is None:
                    fundamentals[ticker] = {
                        'sector': meta.get('sector'),
                        'industry': meta.get('industry'),
                    }
                    continue

                # Get the most recent snapshot available before (date - reporting_lag)
                # This simulates what an investor would actually know at that date
                available_date = (date - timedelta(days=reporting_lag_days)).strftime('%Y-%m-%d')

                query = '''
                    SELECT * FROM fundamental_history
                    WHERE asset_id = ?
                    AND snapshot_date <= ?
                    ORDER BY snapshot_date DESC
                    LIMIT 2
                '''
                cursor = conn.execute(query, (asset_id, available_date))
                col_names = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()

                if not rows:
                    fundamentals[ticker] = {
                        'sector': meta.get('sector'),
                        'industry': meta.get('industry'),
                    }
                    continue

                latest = dict(zip(col_names, rows[0]))
                previous = dict(zip(col_names, rows[1])) if len(rows) > 1 else None

                # Compute P/E from price_history + trailing_eps if pe_ratio is empty
                pe_ratio = latest.get('pe_ratio')
                if pe_ratio is None and latest.get('trailing_eps'):
                    price_on_date = self._get_single_price(ticker, date)
                    if price_on_date and latest['trailing_eps'] > 0:
                        pe_ratio = price_on_date / latest['trailing_eps']

                # Compute revenue_growth from consecutive snapshots
                revenue_growth = latest.get('revenue_growth')
                if revenue_growth is None and previous:
                    prev_rps = previous.get('revenue_per_share')
                    curr_rps = latest.get('revenue_per_share')
                    if prev_rps and curr_rps and prev_rps > 0:
                        revenue_growth = (curr_rps - prev_rps) / prev_rps

                fundamental_data = {
                    'market_cap': latest.get('market_cap'),
                    'pe_ratio': pe_ratio,
                    'pb_ratio': latest.get('price_to_book'),
                    'ps_ratio': latest.get('price_to_sales'),
                    'debt_to_equity': latest.get('debt_to_equity'),
                    'roe': latest.get('return_on_equity'),
                    'roa': latest.get('return_on_assets'),
                    'current_ratio': latest.get('current_ratio'),
                    'quick_ratio': latest.get('quick_ratio'),
                    'gross_margins': latest.get('gross_margins'),
                    'operating_margins': latest.get('operating_margins'),
                    'profit_margins': latest.get('profit_margins'),
                    'revenue_growth': revenue_growth,
                    'earnings_growth': latest.get('earnings_growth'),
                    'free_cash_flow': latest.get('free_cashflow'),
                    'dividend_yield': latest.get('dividend_yield'),
                    'beta': latest.get('beta'),
                    'sector': meta.get('sector'),
                    'industry': meta.get('industry'),
                }

                fundamentals[ticker] = fundamental_data

            conn.close()

        except Exception as e:
            logger.error(f"Error fetching fundamentals from database: {e}")
            # Return empty dicts rather than crashing
            for ticker in tickers:
                if ticker not in fundamentals:
                    fundamentals[ticker] = {}

        return fundamentals

    def _get_single_price(self, ticker: str, date: pd.Timestamp) -> Optional[float]:
        """Get the most recent closing price on or before a given date."""
        try:
            conn = sqlite3.connect(self.db_path)
            query = '''
                SELECT close FROM price_history
                WHERE ticker = ? AND date <= ?
                ORDER BY date DESC LIMIT 1
            '''
            row = conn.execute(query, (ticker, date.strftime('%Y-%m-%d'))).fetchone()
            conn.close()
            return row[0] if row else None
        except Exception:
            return None

    def get_available_tickers_as_of(self, date: pd.Timestamp,
                                       tickers: List[str],
                                       max_gap_calendar_days: int = 7) -> Set[str]:
        """
        Return tickers that have price data on or near the given date.

        A stock is considered 'available' (not delisted) if its most recent
        price_history row is within *max_gap_calendar_days* of *date*
        (roughly 5 trading days).

        Parameters
        ----------
        date : pd.Timestamp
            The as-of date.
        tickers : List[str]
            Candidate tickers to check.
        max_gap_calendar_days : int
            Maximum calendar-day gap allowed between the requested date
            and the ticker's last price entry.  Default 7 (~5 trading days).

        Returns
        -------
        Set[str]
            Tickers that are still actively traded as of *date*.
        """
        if not tickers:
            return set()

        available: Set[str] = set()
        cutoff = (date - timedelta(days=max_gap_calendar_days)).strftime('%Y-%m-%d')
        date_str = date.strftime('%Y-%m-%d')

        try:
            conn = sqlite3.connect(self.db_path)
            # Batch query: for each ticker get the max date <= requested date
            placeholders = ','.join('?' for _ in tickers)
            query = f'''
                SELECT ticker, MAX(date) AS last_date
                FROM price_history
                WHERE ticker IN ({placeholders})
                  AND date <= ?
                GROUP BY ticker
            '''
            rows = conn.execute(query, (*tickers, date_str)).fetchall()
            conn.close()

            for ticker, last_date in rows:
                if last_date >= cutoff:
                    available.add(ticker)
        except Exception as e:
            logger.error(f'Error checking available tickers: {e}')
            # Fail open: treat all as available so the backtest can proceed
            return set(tickers)

        return available

    def _calculate_metrics_as_of(self, tickers: List[str],
                                  price_history: pd.DataFrame,
                                  fundamentals: Dict[str, Dict],
                                  date: pd.Timestamp) -> Dict[str, Dict]:
        """Calculate screening metrics based on point-in-time data."""
        metrics = {}

        for ticker in tickers:
            ticker_metrics = {}

            # Price-based metrics
            if ticker in price_history.columns:
                prices = price_history[ticker].dropna()

                if len(prices) > 0:
                    # Returns
                    ticker_metrics['return_1m'] = (prices.iloc[-1] / prices.iloc[-21] - 1) * 100 if len(prices) > 21 else None
                    ticker_metrics['return_3m'] = (prices.iloc[-1] / prices.iloc[-63] - 1) * 100 if len(prices) > 63 else None
                    ticker_metrics['return_6m'] = (prices.iloc[-1] / prices.iloc[-126] - 1) * 100 if len(prices) > 126 else None
                    ticker_metrics['return_1y'] = (prices.iloc[-1] / prices.iloc[-252] - 1) * 100 if len(prices) > 252 else None

                    # Volatility
                    returns = prices.pct_change()
                    ticker_metrics['volatility'] = returns.std() * np.sqrt(252) * 100

                    # Moving averages
                    ticker_metrics['above_ma50'] = prices.iloc[-1] > prices.rolling(50).mean().iloc[-1] if len(prices) > 50 else None
                    ticker_metrics['above_ma200'] = prices.iloc[-1] > prices.rolling(200).mean().iloc[-1] if len(prices) > 200 else None

                    # Relative strength
                    ticker_metrics['rsi'] = self._calculate_rsi(prices)

            # Fundamental metrics
            if ticker in fundamentals:
                fund_data = fundamentals[ticker]

                # Quality metrics
                ticker_metrics['roe'] = fund_data.get('roe')
                ticker_metrics['roa'] = fund_data.get('roa')
                ticker_metrics['gross_margin'] = fund_data.get('gross_margins')
                ticker_metrics['operating_margin'] = fund_data.get('operating_margins')
                ticker_metrics['current_ratio'] = fund_data.get('current_ratio')
                ticker_metrics['debt_to_equity'] = fund_data.get('debt_to_equity')

                # Value metrics
                ticker_metrics['pe_ratio'] = fund_data.get('pe_ratio')
                ticker_metrics['pb_ratio'] = fund_data.get('pb_ratio')
                ticker_metrics['ps_ratio'] = fund_data.get('ps_ratio')
                ticker_metrics['dividend_yield'] = fund_data.get('dividend_yield')

                # Growth metrics
                ticker_metrics['revenue_growth'] = fund_data.get('revenue_growth')
                ticker_metrics['earnings_growth'] = fund_data.get('earnings_growth')

                # Risk metrics
                ticker_metrics['beta'] = fund_data.get('beta')

                # Other
                ticker_metrics['market_cap'] = fund_data.get('market_cap')
                ticker_metrics['sector'] = fund_data.get('sector')

            metrics[ticker] = ticker_metrics

        return metrics

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI (Relative Strength Index)."""
        if len(prices) < period + 1:
            return None

        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else None
