"""
GBM-based ranking strategy for backtesting.
Uses trained Gradient Boosted Machine models to predict stock returns and rank stocks.
"""

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import lightgbm as lgb
import numpy as np
import pandas as pd

# Add neural_network/training to path for imports
training_path = Path(__file__).parent.parent.parent / 'neural_network' / 'training'
sys.path.insert(0, str(training_path))

from gbm_feature_config import (
    BASE_FEATURES,
    CASHFLOW_FEATURES,
    CATEGORICAL_FEATURES,
    FUNDAMENTAL_FEATURES,
    LAG_PERIODS,
    MARKET_FEATURES,
    PRICE_FEATURES,
    ROLLING_WINDOWS,
)

# Import feature engineering from training (THIS IS THE KEY!)
from train_gbm_stock_ranker import (
    create_change_features,
    create_lag_features,
    create_rolling_features,
    standardize_by_date,
    winsorize_by_date,
)

from backtesting.data.fundamental_history_provider import FundamentalHistoryProvider

logger = logging.getLogger(__name__)


class GBMRankingStrategy:
    """
    Investment strategy using GBM model predictions for stock ranking.

    This strategy:
    1. Loads historical fundamental snapshots (no look-ahead bias)
    2. Engineers same features as training (lags, rolling windows)
    3. Runs GBM model to predict returns
    4. Ranks stocks and selects top performers
    5. Constructs portfolio with configurable weighting
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize GBM ranking strategy.

        Parameters
        ----------
        config : Dict[str, Any], optional
            Strategy configuration including:
            - model_path: Path to trained GBM model file
            - model_type: 'full' or 'lite' (determines min_snapshots requirement)
            - selection_method: 'top_decile', 'top_quintile', 'top_n'
            - num_positions: Number of stocks to hold (if top_n)
            - weighting: 'equal_weight', 'prediction_weighted', 'inverse_volatility'
            - min_prediction: Minimum predicted return to include (default 0.0)
        """
        self.config = config or {}

        # Model configuration
        model_path = self.config.get('model_path')
        if model_path is None:
            raise ValueError('model_path must be specified in config')

        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f'Model not found: {self.model_path}')

        # Load GBM model
        logger.info(f'Loading GBM model from {self.model_path}')
        self.model = lgb.Booster(model_file=str(self.model_path))

        # Model type determines minimum snapshot requirement
        self.model_type = self.config.get('model_type', 'full')
        self.min_snapshots = 12 if self.model_type == 'full' else 4

        # Selection configuration
        self.selection_method = self.config.get('selection_method', 'top_decile')
        self.num_positions = self.config.get('num_positions', 15)
        self.min_prediction = self.config.get('min_prediction', 0.0)

        # Weighting configuration
        self.weighting = self.config.get('weighting', 'equal_weight')

        # Initialize data provider
        self.fundamental_provider = FundamentalHistoryProvider()

        logger.info(f'Initialized GBMRankingStrategy: {self.selection_method}, '
                   f'{self.weighting}, min_snapshots={self.min_snapshots}')

    def generate_signals(self, market_data: Dict[str, Any],
                        current_portfolio: Dict[str, float],
                        date: pd.Timestamp) -> Dict[str, float]:
        """
        Generate target portfolio weights using GBM predictions.

        Uses SAME feature engineering pipeline as training!

        Parameters
        ----------
        market_data : Dict[str, Any]
            Point-in-time market data (not used, we fetch from database)
        current_portfolio : Dict[str, float]
            Current portfolio holdings
        date : pd.Timestamp
            Current date

        Returns
        -------
        Dict[str, float]
            Target weights for each ticker
        """
        logger.info(f'Generating GBM signals for {date}')

        # Load and engineer features using TRAINING PIPELINE
        try:
            features_df = self._load_and_engineer_features(date)

            if len(features_df) == 0:
                logger.warning(f'No features generated for {date}')
                return {}

            logger.info(f'Generated features for {len(features_df)} stocks')

            # Get feature columns - SAME logic as training!
            # Exclude cashflow base features and metadata
            exclude_cols = CASHFLOW_FEATURES + ['ticker', 'snapshot_date', 'snapshot_id']
            numeric_features = [
                col for col in features_df.columns
                if col not in exclude_cols + CATEGORICAL_FEATURES
                and features_df[col].dtype in [np.float64, np.int64, np.float32, np.int32]
            ]

            # Feature matrix: numeric + categorical (same as training)
            feature_cols = numeric_features + CATEGORICAL_FEATURES

            logger.info(f'Using {len(feature_cols)} features for prediction ({len(numeric_features)} numeric + {len(CATEGORICAL_FEATURES)} categorical)')

            # Predict
            X = features_df[feature_cols]
            features_df['predicted_return'] = self.model.predict(X)

            # Select stocks
            pred_df = features_df[['ticker', 'predicted_return']].copy()
            pred_df['volatility'] = 0.0  # TODO: extract from features if needed

            pred_df = pred_df.sort_values('predicted_return', ascending=False)

            logger.info(f'Top prediction: {pred_df.iloc[0]["ticker"]} '
                       f'({pred_df.iloc[0]["predicted_return"]:.2%})')

            selected_stocks = self._select_stocks(pred_df)

            if len(selected_stocks) == 0:
                logger.warning('No stocks selected')
                return {}

            # Calculate weights
            target_weights = self._calculate_weights(selected_stocks)

            logger.info(f'Selected {len(target_weights)} stocks')

            return target_weights

        except Exception as e:
            logger.error(f'Error generating signals: {e}')
            import traceback
            traceback.print_exc()
            return {}

    def _load_and_engineer_features(self, as_of_date: pd.Timestamp) -> pd.DataFrame:
        """
        Load snapshots and engineer features using TRAINING PIPELINE.

        This ensures exact match with training feature engineering!
        """
        # Get database path
        db_path = Path(__file__).parent.parent.parent / 'data' / 'stock_data.db'
        conn = sqlite3.connect(str(db_path))

        # Filing lag: 60 days
        filing_lag_date = as_of_date - pd.Timedelta(days=60)

        # Load snapshots up to filing lag date
        snapshot_cols = (
            ['a.symbol as ticker', 'a.sector', 's.snapshot_date', 's.id as snapshot_id'] +
            [f's.{col}' for col in FUNDAMENTAL_FEATURES + MARKET_FEATURES + CASHFLOW_FEATURES]
        )

        query = f'''
            SELECT
                {', '.join(snapshot_cols)}
            FROM fundamental_history s
            JOIN assets a ON s.asset_id = a.id
            WHERE s.snapshot_date <= '{filing_lag_date.strftime('%Y-%m-%d')}'
            AND s.vix IS NOT NULL
            ORDER BY a.symbol, s.snapshot_date
        '''

        df = pd.read_sql(query, conn)
        df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])

        # Convert numeric columns
        for col in FUNDAMENTAL_FEATURES + MARKET_FEATURES + CASHFLOW_FEATURES:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Load price features from price_history table
        df = self._add_price_features(df, conn, filing_lag_date)

        conn.close()

        if len(df) == 0:
            return pd.DataFrame()

        # Sort by ticker and date
        df = df.sort_values(['ticker', 'snapshot_date']).reset_index(drop=True)

        # Apply TRAINING PIPELINE
        # 1. Computed features
        df['log_market_cap'] = np.log(df['market_cap'].fillna(1e9) + 1e9)
        df['fcf_yield'] = df['free_cashflow'].fillna(0) / (df['market_cap'].fillna(1e9) + 1e9)
        df['ocf_yield'] = df['operating_cashflow'].fillna(0) / (df['market_cap'].fillna(1e9) + 1e9)
        df['earnings_yield'] = df['trailing_eps'].fillna(0) / (df['market_cap'].fillna(1e9) / df['book_value'].fillna(1) + 1e-9)

        # 2. Lag features
        df = create_lag_features(df, BASE_FEATURES, lags=LAG_PERIODS)

        # 3. Change features (QoQ, YoY)
        df = create_change_features(df, BASE_FEATURES)

        # 4. Rolling features
        df = create_rolling_features(df, BASE_FEATURES, windows=ROLLING_WINDOWS)

        # 5. Missingness flags
        for feat in BASE_FEATURES:
            df[f'{feat}_missing'] = df[feat].isna().astype(int)

        # Get most recent snapshot per ticker
        latest_df = df.groupby('ticker').tail(1).reset_index(drop=True)

        # Exclude cashflow base features (only engineered versions are used)
        exclude_cols = CASHFLOW_FEATURES + CATEGORICAL_FEATURES

        # Select numeric features
        numeric_features = [
            col for col in latest_df.columns
            if col not in exclude_cols + ['ticker', 'snapshot_date', 'snapshot_id']
            and latest_df[col].dtype in [np.float64, np.int64, np.float32, np.int32]
        ]

        # Winsorize
        latest_df = winsorize_by_date(latest_df, numeric_features, lower_pct=0.01, upper_pct=0.99)

        # Standardize
        latest_df = standardize_by_date(latest_df, numeric_features)

        # Handle sector categorical
        latest_df['sector'] = latest_df['sector'].fillna('Unknown').astype('category')

        # Keep only tickers with minimum snapshots
        # Count snapshots per ticker in original df
        snapshot_counts = df.groupby('ticker').size()
        valid_tickers = snapshot_counts[snapshot_counts >= self.min_snapshots].index
        latest_df = latest_df[latest_df['ticker'].isin(valid_tickers)]

        logger.info(f'Feature engineering complete: {len(latest_df)} stocks, {len(numeric_features)} features')

        return latest_df

    def _select_stocks(self, pred_df: pd.DataFrame) -> pd.DataFrame:
        """
        Select stocks based on selection method.

        Parameters
        ----------
        pred_df : pd.DataFrame
            DataFrame with columns: ticker, predicted_return, volatility

        Returns
        -------
        pd.DataFrame
            Selected stocks
        """
        # Filter by minimum prediction
        pred_df = pred_df[pred_df['predicted_return'] >= self.min_prediction]

        if len(pred_df) == 0:
            return pd.DataFrame()

        if self.selection_method == 'top_decile':
            # Top 10%
            n = max(1, len(pred_df) // 10)
            return pred_df.head(n)

        elif self.selection_method == 'top_quintile':
            # Top 20%
            n = max(1, len(pred_df) // 5)
            return pred_df.head(n)

        elif self.selection_method == 'top_n':
            # Top N stocks
            return pred_df.head(self.num_positions)

        else:
            raise ValueError(f'Unknown selection method: {self.selection_method}')

    def _calculate_weights(self, selected_stocks: pd.DataFrame) -> Dict[str, float]:
        """
        Calculate portfolio weights for selected stocks.

        Parameters
        ----------
        selected_stocks : pd.DataFrame
            Selected stocks with predicted_return and volatility

        Returns
        -------
        Dict[str, float]
            Ticker -> weight mapping
        """
        if len(selected_stocks) == 0:
            return {}

        if self.weighting == 'equal_weight':
            # Equal weight all positions
            weight = 1.0 / len(selected_stocks)
            return {row['ticker']: weight for _, row in selected_stocks.iterrows()}

        elif self.weighting == 'prediction_weighted':
            # Weight by predicted return (higher return = higher weight)
            # Normalize predictions to [0, 1] range
            pred_values = selected_stocks['predicted_return'].values
            min_pred = pred_values.min()
            max_pred = pred_values.max()

            if max_pred > min_pred:
                normalized = (pred_values - min_pred) / (max_pred - min_pred)
            else:
                normalized = np.ones(len(pred_values))

            # Add small constant to avoid zero weights
            normalized = normalized + 0.1

            # Normalize to sum to 1.0
            weights = normalized / normalized.sum()

            return {
                row['ticker']: float(weights[i])
                for i, (_, row) in enumerate(selected_stocks.iterrows())
            }

        elif self.weighting == 'inverse_volatility':
            # Weight inversely to volatility (lower vol = higher weight)
            vol_values = selected_stocks['volatility'].values

            # Handle zero volatility
            vol_values = np.maximum(vol_values, 0.01)

            # Inverse volatility
            inv_vol = 1.0 / vol_values

            # Normalize to sum to 1.0
            weights = inv_vol / inv_vol.sum()

            return {
                row['ticker']: float(weights[i])
                for i, (_, row) in enumerate(selected_stocks.iterrows())
            }

        else:
            raise ValueError(f'Unknown weighting method: {self.weighting}')

    def _add_price_features(self, df: pd.DataFrame, conn, as_of_date: pd.Timestamp) -> pd.DataFrame:
        """
        Add price-based features by loading from price_history table.

        Features added:
        - returns_1m, returns_3m, returns_6m, returns_1y
        - volatility (annualized standard deviation of daily returns)
        - volume_trend (ratio of recent to historical average volume)
        """
        # Initialize all price features to 0
        for feat in PRICE_FEATURES:
            df[feat] = 0.0

        # Get unique tickers from df
        tickers = df['ticker'].unique()

        # For each ticker, calculate price features as of as_of_date
        for ticker in tickers:
            try:
                # Query price history up to as_of_date
                # Need at least 1 year of data for all features
                start_date = as_of_date - pd.Timedelta(days=365)

                price_query = '''
                    SELECT date, close, volume
                    FROM price_history
                    WHERE ticker = ?
                    AND date >= ?
                    AND date <= ?
                    ORDER BY date
                '''

                prices = pd.read_sql(
                    price_query,
                    conn,
                    params=(ticker, start_date.strftime('%Y-%m-%d'), as_of_date.strftime('%Y-%m-%d')),
                    parse_dates=['date'],
                    index_col='date'
                )

                if len(prices) < 20:  # Need at least 20 days of data
                    continue

                # Calculate returns
                current_price = prices['close'].iloc[-1]

                # 1-month return (21 trading days)
                if len(prices) >= 21:
                    price_1m_ago = prices['close'].iloc[-21]
                    df.loc[df['ticker'] == ticker, 'returns_1m'] = (current_price / price_1m_ago - 1) * 100

                # 3-month return (63 trading days)
                if len(prices) >= 63:
                    price_3m_ago = prices['close'].iloc[-63]
                    df.loc[df['ticker'] == ticker, 'returns_3m'] = (current_price / price_3m_ago - 1) * 100

                # 6-month return (126 trading days)
                if len(prices) >= 126:
                    price_6m_ago = prices['close'].iloc[-126]
                    df.loc[df['ticker'] == ticker, 'returns_6m'] = (current_price / price_6m_ago - 1) * 100

                # 1-year return (252 trading days)
                if len(prices) >= 252:
                    price_1y_ago = prices['close'].iloc[-252]
                    df.loc[df['ticker'] == ticker, 'returns_1y'] = (current_price / price_1y_ago - 1) * 100

                # Volatility (annualized)
                daily_returns = prices['close'].pct_change().dropna()
                if len(daily_returns) > 0:
                    volatility = daily_returns.std() * np.sqrt(252) * 100  # Annualized percentage
                    df.loc[df['ticker'] == ticker, 'volatility'] = volatility

                # Volume trend (recent 20 days vs previous 100 days)
                if len(prices) >= 120:
                    recent_volume = prices['volume'].iloc[-20:].mean()
                    historical_volume = prices['volume'].iloc[-120:-20].mean()
                    if historical_volume > 0:
                        volume_trend = recent_volume / historical_volume
                        df.loc[df['ticker'] == ticker, 'volume_trend'] = volume_trend

            except Exception as e:
                logger.debug(f'Could not calculate price features for {ticker}: {e}')
                continue

        return df
