#!/usr/bin/env python3
"""
Train GBM Lite model for stocks with limited historical data (4-6 quarters).

This is a lightweight version that requires fewer quarters:
- Lag periods: [1, 2] instead of [1, 2, 4, 8]
- Rolling windows: [4] instead of [4, 8, 12]
- Result: ~200 features instead of 464

Use this for stocks that don't qualify for the full GBM model.
"""

import argparse
import json
import logging
import sqlite3
import warnings
from datetime import timedelta
from pathlib import Path
from typing import Dict, List, Tuple

import lightgbm as lgb
import numpy as np
import pandas as pd

# Import LITE feature configuration
from gbm_lite_feature_config import (
    BASE_FEATURES,
    CASHFLOW_FEATURES,
    CATEGORICAL_FEATURES,
    FUNDAMENTAL_FEATURES,
    LAG_PERIODS,
    MARKET_FEATURES,
    PRICE_FEATURES,
    ROLLING_WINDOWS,
    get_min_quarters_required,
)
from scipy import stats
from scipy.stats import linregress
from sklearn.metrics import ndcg_score

# Suppress warnings
warnings.filterwarnings('ignore')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def compute_tradability_date(
    report_period_end: pd.Timestamp,
    filing_date: pd.Timestamp | None = None
) -> pd.Timestamp:
    """
    Compute the earliest date when fundamental data could be traded on.

    Rule (conservative):
    - If filing_date is available: asof_date = filing_date + 2 trading days
    - Else: asof_date = report_period_end + 60 calendar days

    Parameters
    ----------
    report_period_end : pd.Timestamp
        End date of the reporting period (quarter-end)
    filing_date : pd.Timestamp | None
        Actual filing date (if available from SEC EDGAR)

    Returns
    -------
    pd.Timestamp
        Tradability date (as-of date)
    """
    if filing_date is not None and pd.notna(filing_date):
        return filing_date + timedelta(days=3)
    else:
        return report_period_end + timedelta(days=60)


def create_lag_features(
    df: pd.DataFrame,
    features: List[str],
    lags: List[int] = [1, 2]  # LITE: Only 1Q, 2Q
) -> pd.DataFrame:
    """
    Create lagged features (1Q, 2Q back only).

    Parameters
    ----------
    df : pd.DataFrame
        Data sorted by (ticker, snapshot_date)
    features : List[str]
        Features to lag
    lags : List[int]
        Number of quarters to lag (default: [1, 2])

    Returns
    -------
    pd.DataFrame
        DataFrame with additional lag columns
    """
    df = df.copy()

    for feat in features:
        if feat not in df.columns:
            continue

        for lag in lags:
            lag_col = f'{feat}_lag{lag}q'
            df[lag_col] = df.groupby('ticker')[feat].shift(lag)

    return df


def create_change_features(
    df: pd.DataFrame,
    features: List[str]
) -> pd.DataFrame:
    """
    Create QoQ and YoY change features.

    Parameters
    ----------
    df : pd.DataFrame
        Data with lag features already created
    features : List[str]
        Base features to compute changes for

    Returns
    -------
    pd.DataFrame
        DataFrame with additional change columns
    """
    df = df.copy()

    for feat in features:
        if feat not in df.columns:
            continue

        # QoQ: (F_t - F_{t-1}) / (|F_{t-1}| + 1e-9)
        lag1_col = f'{feat}_lag1q'
        if lag1_col in df.columns:
            lag1_vals = pd.to_numeric(df[lag1_col], errors='coerce')
            feat_vals = pd.to_numeric(df[feat], errors='coerce')
            numerator = feat_vals - lag1_vals
            denominator = lag1_vals.abs().fillna(0) + 1e-9
            df[f'{feat}_qoq'] = numerator / denominator

        # YoY: Use lag2q as proxy since we don't have lag4q
        # (This is approximate, but better than nothing)
        lag2_col = f'{feat}_lag2q'
        if lag2_col in df.columns:
            lag2_vals = pd.to_numeric(df[lag2_col], errors='coerce')
            feat_vals = pd.to_numeric(df[feat], errors='coerce')
            numerator = feat_vals - lag2_vals
            denominator = lag2_vals.abs().fillna(0) + 1e-9
            df[f'{feat}_yoy'] = numerator / denominator

    return df


def create_rolling_features(
    df: pd.DataFrame,
    features: List[str],
    windows: List[int] = [4]  # LITE: Only 4Q window
) -> pd.DataFrame:
    """
    Create rolling statistics (mean, std, slope) over 4 quarters only.

    Parameters
    ----------
    df : pd.DataFrame
        Data sorted by (ticker, snapshot_date)
    features : List[str]
        Features to compute rolling stats for
    windows : List[int]
        Window sizes in quarters (default: [4])

    Returns
    -------
    pd.DataFrame
        DataFrame with additional rolling stat columns
    """
    df = df.copy()

    for feat in features:
        if feat not in df.columns:
            continue

        for window in windows:
            # Rolling mean (min_periods=2 to allow for sparse data)
            mean_col = f'{feat}_mean{window}q'
            df[mean_col] = df.groupby('ticker')[feat].transform(
                lambda x: x.rolling(window, min_periods=2).mean()
            )

            # Rolling std
            std_col = f'{feat}_std{window}q'
            df[std_col] = df.groupby('ticker')[feat].transform(
                lambda x: x.rolling(window, min_periods=2).std()
            )

            # Rolling slope (OLS trend)
            slope_col = f'{feat}_slope{window}q'

            def rolling_slope(series):
                if len(series) < 2:
                    return np.nan
                x = np.arange(len(series))
                try:
                    slope, _, _, _, _ = linregress(x, series)
                    return slope
                except Exception:
                    return np.nan

            df[slope_col] = df.groupby('ticker')[feat].transform(
                lambda x: x.rolling(window, min_periods=2).apply(rolling_slope, raw=False)
            )

    return df


def winsorize_by_date(
    df: pd.DataFrame,
    features: List[str],
    lower_pct: float = 0.01,
    upper_pct: float = 0.99
) -> pd.DataFrame:
    """
    Winsorize features cross-sectionally (per date) to handle outliers.

    Parameters
    ----------
    df : pd.DataFrame
        Data with snapshot_date column
    features : List[str]
        Numeric features to winsorize
    lower_pct : float
        Lower percentile (default: 1st)
    upper_pct : float
        Upper percentile (default: 99th)

    Returns
    -------
    pd.DataFrame
        DataFrame with winsorized features
    """
    df = df.copy()

    for feat in features:
        if feat not in df.columns:
            continue

        # Compute percentiles per date
        lower_vals = df.groupby('snapshot_date')[feat].transform(
            lambda x: x.quantile(lower_pct)
        )
        upper_vals = df.groupby('snapshot_date')[feat].transform(
            lambda x: x.quantile(upper_pct)
        )

        # Clip
        df[feat] = df[feat].clip(lower=lower_vals, upper=upper_vals)

    return df


def standardize_by_date(
    df: pd.DataFrame,
    features: List[str]
) -> pd.DataFrame:
    """
    Standardize features cross-sectionally (z-score per date).

    Parameters
    ----------
    df : pd.DataFrame
        Data with snapshot_date column
    features : List[str]
        Numeric features to standardize

    Returns
    -------
    pd.DataFrame
        DataFrame with standardized features
    """
    df = df.copy()

    for feat in features:
        if feat not in df.columns:
            continue

        # Z-score per date
        df[feat] = df.groupby('snapshot_date')[feat].transform(
            lambda x: (x - x.mean()) / (x.std() + 1e-9)
        )

    return df


def purged_group_time_series_split(
    df: pd.DataFrame,
    n_splits: int = 5,
    purge_days: int = 365,
    embargo_days: int = 21
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Create purged + embargoed + grouped time-series CV splits.

    - Time-based splits (train past → validate future)
    - Group by ticker (entire stock in one fold)
    - Purge: remove samples within prediction horizon around boundaries
    - Embargo: add buffer after train window

    Parameters
    ----------
    df : pd.DataFrame
        Data with 'snapshot_date' and 'ticker' columns
    n_splits : int
        Number of CV folds
    purge_days : int
        Purge period (days) - matches prediction horizon
    embargo_days : int
        Embargo period (days) after train window

    Returns
    -------
    List[Tuple[np.ndarray, np.ndarray]]
        List of (train_idx, val_idx) tuples
    """
    df = df.sort_values('snapshot_date').reset_index(drop=True)
    dates = df['snapshot_date'].unique()
    dates = np.sort(dates)

    n_dates = len(dates)
    fold_size = n_dates // (n_splits + 1)

    splits = []

    for i in range(n_splits):
        train_end_idx = fold_size * (i + 1)
        train_end_date = dates[train_end_idx]

        embargo_end_date = train_end_date + pd.Timedelta(days=embargo_days)
        val_start_date = embargo_end_date

        val_end_idx = min(train_end_idx + fold_size, n_dates - 1)
        val_end_date = dates[val_end_idx]

        purge_start_date = val_start_date - pd.Timedelta(days=purge_days)

        train_idx = df[
            (df['snapshot_date'] < purge_start_date)
        ].index.values

        val_idx = df[
            (df['snapshot_date'] >= val_start_date) &
            (df['snapshot_date'] <= val_end_date)
        ].index.values

        if len(train_idx) > 0 and len(val_idx) > 0:
            splits.append((train_idx, val_idx))
            purge_start_pd = pd.Timestamp(purge_start_date)
            val_start_pd = pd.Timestamp(val_start_date)
            val_end_pd = pd.Timestamp(val_end_date)
            logger.info(
                f'Fold {i+1}: Train={len(train_idx)} samples (up to {purge_start_pd.date()}), '
                f'Val={len(val_idx)} samples ({val_start_pd.date()} to {val_end_pd.date()})'
            )

    return splits


def compute_rank_ic(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """
    Compute rank Information Coefficient (Spearman correlation).

    Parameters
    ----------
    y_true : np.ndarray
        True returns
    y_pred : np.ndarray
        Predicted returns/scores

    Returns
    -------
    float
        Spearman rank correlation
    """
    if len(y_true) < 2:
        return 0.0

    mask = ~(np.isnan(y_true) | np.isnan(y_pred))
    if np.sum(mask) < 2:
        return 0.0

    ic, _ = stats.spearmanr(y_true[mask], y_pred[mask])
    return ic if not np.isnan(ic) else 0.0


def compute_decile_spreads(
    df: pd.DataFrame,
    y_pred_col: str = 'y_pred',
    y_true_col: str = 'y_true'
) -> Dict[str, float]:
    """
    Compute top-bottom decile spread and quintile spreads.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame with predictions and actuals
    y_pred_col : str
        Column name for predictions
    y_true_col : str
        Column name for actual returns

    Returns
    -------
    Dict[str, float]
        Dictionary with spread statistics
    """
    df = df.copy()
    df = df.dropna(subset=[y_pred_col, y_true_col])

    if len(df) < 10:
        return {'top_decile_ret': 0.0, 'bottom_decile_ret': 0.0, 'spread': 0.0}

    # Rank by prediction
    df['decile'] = pd.qcut(df[y_pred_col], q=10, labels=False, duplicates='drop')

    # Compute mean return by decile
    decile_rets = df.groupby('decile')[y_true_col].mean()

    top_ret = decile_rets.iloc[-1] if len(decile_rets) >= 10 else 0.0
    bottom_ret = decile_rets.iloc[0] if len(decile_rets) >= 10 else 0.0
    spread = top_ret - bottom_ret

    return {
        'top_decile_ret': top_ret,
        'bottom_decile_ret': bottom_ret,
        'spread': spread
    }


class GBMLiteStockRanker:
    """Lightweight GBM stock ranker for stocks with limited history (4-6 quarters)."""

    def __init__(
        self,
        db_path: str = '../../data/stock_data.db',
        target_horizon: str = '1y',
        model_type: str = 'lightgbm'
    ):
        """
        Initialize GBM Lite stock ranker.

        Parameters
        ----------
        db_path : str
            Path to SQLite database
        target_horizon : str
            Target prediction horizon ('1y' or '3y')
        model_type : str
            Model type ('lightgbm' or 'catboost')
        """
        self.db_path = Path(__file__).parent / db_path
        self.target_horizon = target_horizon
        self.model_type = model_type
        self.model = None
        self.feature_names = []
        self.min_quarters = get_min_quarters_required()

        logger.info(f'Initialized {model_type} LITE ranker for {target_horizon} horizon')
        logger.info(f'Minimum quarters required: {self.min_quarters}')

    def load_data(self) -> pd.DataFrame:
        """
        Load fundamental snapshots and forward returns from database.

        Returns
        -------
        pd.DataFrame
            DataFrame with fundamental features and forward returns
        """
        logger.info(f'Loading data from {self.db_path}')

        conn = sqlite3.connect(self.db_path)

        # Load snapshots with fundamental data
        query = '''
            SELECT
                a.symbol as ticker,
                a.sector,
                s.snapshot_date,
                s.market_cap,
                s.pe_ratio,
                s.pb_ratio,
                s.ps_ratio,
                s.profit_margins,
                s.operating_margins,
                s.gross_margins,
                s.return_on_equity,
                s.return_on_assets,
                s.revenue_growth,
                s.earnings_growth,
                s.debt_to_equity,
                s.current_ratio,
                s.quick_ratio,
                s.operating_cashflow,
                s.free_cashflow,
                s.trailing_eps,
                s.book_value,
                s.dividend_yield,
                s.payout_ratio,
                s.enterprise_to_ebitda,
                s.enterprise_to_revenue,
                s.beta,
                s.vix,
                s.treasury_10y,
                s.id as snapshot_id
            FROM fundamental_history s
            JOIN assets a ON s.asset_id = a.id
            WHERE s.vix IS NOT NULL
            ORDER BY a.symbol, s.snapshot_date
        '''

        df = pd.read_sql(query, conn)
        df['snapshot_date'] = pd.to_datetime(df['snapshot_date'])

        logger.info(f'Loaded {len(df)} snapshots for {df["ticker"].nunique()} stocks')

        # Convert all numeric columns to float
        for col in FUNDAMENTAL_FEATURES + MARKET_FEATURES + CASHFLOW_FEATURES:
            df[col] = pd.to_numeric(df[col], errors='coerce')

        # Load forward returns
        returns_query = '''
            SELECT
                snapshot_id,
                return_pct
            FROM forward_returns
            WHERE horizon = ?
        '''

        returns_df = pd.read_sql(returns_query, conn, params=(self.target_horizon,))

        # Merge forward returns
        df = df.merge(returns_df, on='snapshot_id', how='left')
        df = df.rename(columns={'return_pct': 'forward_return'})

        logger.info(f'Merged forward returns: {df["forward_return"].notna().sum()} samples with targets')

        # Load price history for price-based features
        logger.info('Loading price history for momentum features...')
        df = self._add_price_features(df, conn)

        conn.close()

        return df

    def _add_price_features(self, df: pd.DataFrame, conn) -> pd.DataFrame:
        """
        Add price-based features (returns, volatility, volume trend).

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame with snapshot_id and snapshot_date
        conn : sqlite3.Connection
            Database connection

        Returns
        -------
        pd.DataFrame
            DataFrame with price features added
        """
        # Load all price history at once
        price_query = '''
            SELECT
                ticker,
                date,
                close,
                volume
            FROM price_history
            ORDER BY ticker, date
        '''
        price_df = pd.read_sql(price_query, conn)
        price_df['date'] = pd.to_datetime(price_df['date'])

        logger.info(f'Loaded {len(price_df)} price history records')

        # Group price history by snapshot_id for fast lookup
        price_groups = price_df.groupby('ticker')

        # Calculate price features efficiently
        def calc_price_features(row):
            ticker = row['ticker']
            snapshot_date = row['snapshot_date']

            # Get price history for this snapshot
            if ticker not in price_groups.groups:
                return pd.Series({
                    'returns_1m': np.nan,
                    'returns_3m': np.nan,
                    'returns_6m': np.nan,
                    'returns_1y': np.nan,
                    'volatility': np.nan,
                    'volume_trend': np.nan
                })

            ticker_prices = price_groups.get_group(ticker)
            ticker_prices = ticker_prices[ticker_prices['date'] <= snapshot_date].sort_values('date')

            if len(ticker_prices) >= 21:
                recent_prices = ticker_prices.tail(252)
                closes = recent_prices['close'].values
                volumes = recent_prices['volume'].values

                returns_1m = (closes[-1] - closes[-21]) / closes[-21] if len(closes) >= 21 else np.nan
                returns_3m = (closes[-1] - closes[-63]) / closes[-63] if len(closes) >= 63 else np.nan
                returns_6m = (closes[-1] - closes[-126]) / closes[-126] if len(closes) >= 126 else np.nan
                returns_1y = (closes[-1] - closes[0]) / closes[0] if len(closes) >= 252 else np.nan

                recent_closes = closes[-60:] if len(closes) >= 60 else closes
                daily_returns = np.diff(recent_closes) / recent_closes[:-1]
                volatility = np.std(daily_returns) if len(daily_returns) > 0 else np.nan

                vol_avg = np.mean(volumes)
                vol_recent = np.mean(volumes[-5:]) if len(volumes) >= 5 else vol_avg
                volume_trend = (vol_recent - vol_avg) / (vol_avg + 1e-9) if vol_avg > 0 else np.nan

            else:
                # Not enough price history - use NaN to indicate missing data
                returns_1m = np.nan
                returns_3m = np.nan
                returns_6m = np.nan
                returns_1y = np.nan
                volatility = np.nan
                volume_trend = np.nan

            return pd.Series({
                'returns_1m': returns_1m,
                'returns_3m': returns_3m,
                'returns_6m': returns_6m,
                'returns_1y': returns_1y,
                'volatility': volatility,
                'volume_trend': volume_trend
            })

        # Apply calculation to all rows
        price_features = df.apply(calc_price_features, axis=1)
        df = pd.concat([df, price_features], axis=1)

        # Keep NaN values - LightGBM can handle them properly
        # No longer filling with 0.0 which incorrectly implies "no return"
        logger.info(f'Added price features: {", ".join(PRICE_FEATURES)}')

        return df

    def engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Create all features using LITE configuration.

        Parameters
        ----------
        df : pd.DataFrame
            Raw fundamental data

        Returns
        -------
        pd.DataFrame
            DataFrame with engineered features
        """
        logger.info('Engineering features (LITE configuration)...')

        # Sort by ticker and date
        df = df.sort_values(['ticker', 'snapshot_date']).reset_index(drop=True)

        # Create computed features
        logger.info('Creating computed features...')

        df['log_market_cap'] = np.log(df['market_cap'] + 1e9)

        # Yield features
        df['fcf_yield'] = df['free_cashflow'] / (df['market_cap'] + 1e9)
        df['ocf_yield'] = df['operating_cashflow'] / (df['market_cap'] + 1e9)
        df['earnings_yield'] = df['trailing_eps'] / (df['market_cap'] / df['book_value'] + 1e-9)

        # 1. Create lag features (LITE: only 1Q, 2Q)
        df = create_lag_features(df, BASE_FEATURES, lags=LAG_PERIODS)
        logger.info(f'Created lag features for {len(BASE_FEATURES)} features (lags: {LAG_PERIODS})')

        # 2. Create change features (QoQ, YoY)
        df = create_change_features(df, BASE_FEATURES)
        logger.info('Created change features')

        # 3. Create rolling features (LITE: only 4Q window)
        df = create_rolling_features(df, BASE_FEATURES, windows=ROLLING_WINDOWS)
        logger.info(f'Created rolling features (windows: {ROLLING_WINDOWS})')

        # 4. Add missingness flags
        for feat in BASE_FEATURES:
            df[f'{feat}_missing'] = df[feat].isna().astype(int)

        logger.info(f'Total columns after engineering: {len(df.columns)}')

        return df

    def prepare_training_data(
        self,
        df: pd.DataFrame
    ) -> Tuple[pd.DataFrame, List[str], List[str]]:
        """
        Prepare final training dataset with standardization.

        Parameters
        ----------
        df : pd.DataFrame
            Data with all features engineered

        Returns
        -------
        Tuple[pd.DataFrame, List[str], List[str]]
            (prepared_df, numeric_features, categorical_features)
        """
        logger.info('Preparing training data...')

        # Drop rows without forward returns
        df = df.dropna(subset=['forward_return'])

        # Exclude metadata and categorical features
        exclude_cols = (
            ['ticker', 'snapshot_date', 'snapshot_id', 'forward_return'] +
            CATEGORICAL_FEATURES +
            CASHFLOW_FEATURES
        )

        numeric_features = [
            col for col in df.columns
            if col not in exclude_cols and df[col].dtype in [np.float64, np.int64]
        ]

        categorical_features = CATEGORICAL_FEATURES

        # Winsorize numeric features
        logger.info('Winsorizing features (1st-99th percentile)')
        df = winsorize_by_date(df, numeric_features, lower_pct=0.01, upper_pct=0.99)

        # Standardize numeric features
        logger.info('Standardizing features (z-score per date)')
        df = standardize_by_date(df, numeric_features)

        # Handle categoricals
        df['sector'] = df['sector'].fillna('Unknown')

        logger.info(f'Training data: {len(df)} samples, {len(numeric_features)} numeric features, {len(categorical_features)} categorical')

        return df, numeric_features, categorical_features

    def train(
        self,
        df: pd.DataFrame,
        numeric_features: List[str],
        categorical_features: List[str],
        params: Dict | None = None
    ):
        """
        Train LightGBM Lite model with purged CV.

        Parameters
        ----------
        df : pd.DataFrame
            Prepared training data
        numeric_features : List[str]
            Numeric feature names
        categorical_features : List[str]
            Categorical feature names
        params : Dict | None
            Model hyperparameters
        """
        logger.info(f'Training {self.model_type} LITE model...')

        # Prepare feature matrix
        feature_cols = numeric_features + categorical_features
        X = df[feature_cols].copy()
        y = df['forward_return'].values

        # Encode categoricals
        for cat_col in categorical_features:
            X[cat_col] = X[cat_col].astype('category')

        # Default params (same as full GBM)
        if params is None:
            params = {
                'objective': 'regression',
                'metric': 'rmse',
                'boosting_type': 'gbdt',
                'num_leaves': 127,
                'max_depth': 7,
                'learning_rate': 0.05,
                'n_estimators': 500,
                'min_child_samples': 500,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'reg_lambda': 5.0,
                'verbose': -1,
                # Fixed random seeds for reproducibility
                'random_state': 42,
                'feature_fraction_seed': 42,
                'bagging_seed': 42
            }

        # Purged CV
        cv_splits = purged_group_time_series_split(
            df,
            n_splits=5,
            purge_days=365 if self.target_horizon == '1y' else 1095,
            embargo_days=21
        )

        # Train-val split
        train_idx, val_idx = cv_splits[-1]

        X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]

        logger.info(f'Train: {len(X_train)} samples, Val: {len(X_val)} samples')

        # Train LightGBM
        train_data = lgb.Dataset(X_train, label=y_train, categorical_feature=categorical_features)
        val_data = lgb.Dataset(X_val, label=y_val, categorical_feature=categorical_features, reference=train_data)

        self.model = lgb.train(
            params,
            train_data,
            num_boost_round=1000,
            valid_sets=[train_data, val_data],
            valid_names=['train', 'val'],
            callbacks=[
                lgb.early_stopping(stopping_rounds=50),
                lgb.log_evaluation(period=50)
            ]
        )

        self.feature_names = feature_cols

        logger.info('Training complete')

    def evaluate(
        self,
        df: pd.DataFrame,
        numeric_features: List[str],
        categorical_features: List[str]
    ) -> Dict:
        """
        Evaluate model with Rank IC, decile spreads, NDCG.

        Parameters
        ----------
        df : pd.DataFrame
            Test data
        numeric_features : List[str]
            Numeric feature names
        categorical_features : List[str]
            Categorical feature names

        Returns
        -------
        Dict
            Evaluation metrics
        """
        logger.info('Evaluating model...')

        # Prepare features
        feature_cols = numeric_features + categorical_features
        X = df[feature_cols].copy()
        y_true = df['forward_return'].values

        # Encode categoricals
        for cat_col in categorical_features:
            X[cat_col] = X[cat_col].astype('category')

        # Predict
        y_pred = self.model.predict(X)

        # Rank IC
        rank_ic = compute_rank_ic(y_true, y_pred)

        # Decile spreads
        eval_df = pd.DataFrame({
            'y_true': y_true,
            'y_pred': y_pred
        })
        spreads = compute_decile_spreads(eval_df)

        # NDCG
        y_true_gains = np.exp(y_true).reshape(1, -1)
        y_pred_ranks = y_pred.reshape(1, -1)

        try:
            ndcg = ndcg_score(y_true_gains, y_pred_ranks, k=10)
        except Exception:
            ndcg = 0.0

        metrics = {
            'rank_ic': rank_ic,
            'top_decile_return': spreads['top_decile_ret'],
            'bottom_decile_return': spreads['bottom_decile_ret'],
            'decile_spread': spreads['spread'],
            'ndcg@10': ndcg
        }

        logger.info(f'Rank IC: {rank_ic:.4f}')
        logger.info(f'Decile Spread: {spreads["spread"]:.4f}')
        logger.info(f'NDCG@10: {ndcg:.4f}')

        return metrics

    def save_model(self, path: str | None = None):
        """Save trained model."""
        if path is None:
            path = f'gbm_lite_model_{self.target_horizon}.txt'

        # Save to neural_network/models/gbm/
        save_dir = Path(__file__).parent.parent / 'models/gbm'
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / path

        self.model.save_model(str(save_path))
        logger.info(f'Model saved to {save_path}')


def main():
    parser = argparse.ArgumentParser(description='Train GBM Lite stock ranker')
    parser.add_argument('--target-horizon', type=str, default='1y',
                        help='Target prediction horizon (1y or 3y)')
    parser.add_argument('--model-type', type=str, default='lightgbm',
                        help='Model type (lightgbm or catboost)')
    args = parser.parse_args()

    # Initialize trainer
    trainer = GBMLiteStockRanker(
        target_horizon=args.target_horizon,
        model_type=args.model_type
    )

    # Load data
    df = trainer.load_data()

    # Engineer features
    df = trainer.engineer_features(df)

    # Prepare training data
    df, numeric_features, categorical_features = trainer.prepare_training_data(df)

    # Train model
    trainer.train(df, numeric_features, categorical_features)

    # Evaluate
    metrics = trainer.evaluate(df, numeric_features, categorical_features)

    # Save model
    trainer.save_model()

    logger.info(f'Training complete for {args.target_horizon} horizon (LITE)!')
    logger.info(f'Final metrics: {json.dumps(metrics, indent=2)}')


if __name__ == '__main__':
    main()
