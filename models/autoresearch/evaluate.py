"""
Fixed evaluation harness for autoresearch stock return prediction.
DO NOT MODIFY — this is the read-only ground truth, like prepare.py in Karpathy's setup.

Target: peak return within a 2-year forward window.
    peak_return = max(close[t : t + 504 trading days]) / close[t] - 1

Metric: Spearman rank correlation between predicted and actual peak returns.
    Higher is better. A perfect ranker scores 1.0.

Usage:
    # From train.py:
    from evaluate import load_data, score_predictions, print_results

    train_df, test_df, feature_cols = load_data()
    # ... train your model on train_df, predict on test_df ...
    results = score_predictions(test_df['peak_return_2y'], predictions)
    print_results(results)
"""

import os
import time
import sqlite3
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

# ---------------------------------------------------------------------------
# Constants (fixed, do not modify)
# ---------------------------------------------------------------------------

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'stock_data.db')
FORWARD_DAYS = 504          # ~2 years of trading days
TRAIN_CUTOFF = '2022-01-01' # train on snapshots before this date
TEST_END = '2024-01-01'     # test on snapshots in [TRAIN_CUTOFF, TEST_END)
TIME_BUDGET = 120           # seconds — training + prediction must finish within this

# Fundamental features available in fundamental_history
FUNDAMENTAL_COLS = [
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
    'price_change_pct', 'volatility', 'beta',
    'fifty_day_average', 'two_hundred_day_average',
    'fifty_two_week_high', 'fifty_two_week_low',
    'vix', 'treasury_10y', 'dollar_index', 'oil_price', 'gold_price',
]


# ---------------------------------------------------------------------------
# Data loading & target computation
# ---------------------------------------------------------------------------

def _load_raw():
    """Load fundamental_history and price_history from SQLite."""
    conn = sqlite3.connect(DB_PATH)

    # Load fundamentals with ticker info
    fund_df = pd.read_sql_query("""
        SELECT f.*, a.symbol as ticker, a.sector, a.industry
        FROM fundamental_history f
        JOIN assets a ON f.asset_id = a.id
        WHERE f.vix IS NOT NULL
        ORDER BY a.symbol, f.snapshot_date
    """, conn)
    fund_df['snapshot_date'] = pd.to_datetime(fund_df['snapshot_date'])

    # Load price history
    price_df = pd.read_sql_query("""
        SELECT ticker, date, close
        FROM price_history
        WHERE close IS NOT NULL
        ORDER BY ticker, date
    """, conn)
    price_df['date'] = pd.to_datetime(price_df['date'])

    conn.close()
    return fund_df, price_df


def _compute_peak_returns(fund_df, price_df):
    """Compute peak return in 2-year forward window for each snapshot."""
    peak_returns = []

    for ticker, group in price_df.groupby('ticker'):
        group = group.sort_values('date').reset_index(drop=True)
        closes = group['close'].values
        dates = group['date'].values

        # For each snapshot of this ticker, find peak forward return
        ticker_snapshots = fund_df[fund_df['ticker'] == ticker]
        for _, row in ticker_snapshots.iterrows():
            snap_date = row['snapshot_date']

            # Find the price index at or after snapshot date
            idx = np.searchsorted(dates, snap_date)
            if idx >= len(dates):
                continue

            baseline_price = closes[idx]
            if baseline_price <= 0:
                continue

            # Forward window: next FORWARD_DAYS trading days
            end_idx = min(idx + FORWARD_DAYS, len(closes))
            if end_idx - idx < 63:  # need at least ~3 months of forward data
                continue

            peak_price = closes[idx:end_idx].max()
            peak_ret = (peak_price / baseline_price) - 1.0
            peak_returns.append((row['id'], peak_ret))

    return dict(peak_returns)


def _add_price_features(fund_df, price_df):
    """Add momentum and technical features from price history."""
    price_features = []

    for ticker, group in price_df.groupby('ticker'):
        group = group.sort_values('date').reset_index(drop=True)
        closes = group['close'].values
        dates = group['date'].values
        volumes = group.get('volume', pd.Series(dtype=float)).values if 'volume' in group.columns else None

        ticker_snapshots = fund_df[fund_df['ticker'] == ticker]
        for _, row in ticker_snapshots.iterrows():
            snap_date = row['snapshot_date']
            idx = np.searchsorted(dates, snap_date)
            if idx < 21:  # need some history
                continue

            price_now = closes[min(idx, len(closes) - 1)]
            if price_now <= 0:
                continue

            feats = {'id': row['id']}

            # Returns over various lookbacks
            for name, lookback in [('ret_1m', 21), ('ret_3m', 63), ('ret_6m', 126), ('ret_1y', 252)]:
                if idx >= lookback:
                    feats[name] = (price_now / closes[idx - lookback]) - 1.0
                else:
                    feats[name] = np.nan

            # Volatility (60-day)
            start = max(0, idx - 60)
            daily_rets = np.diff(closes[start:idx + 1]) / closes[start:idx]
            feats['vol_60d'] = np.std(daily_rets) * np.sqrt(252) if len(daily_rets) > 5 else np.nan

            # Distance from 52-week high/low
            if idx >= 252:
                hi = closes[idx - 252:idx + 1].max()
                lo = closes[idx - 252:idx + 1].min()
                feats['dist_52w_high'] = (price_now / hi) - 1.0
                feats['dist_52w_low'] = (price_now / lo) - 1.0
            else:
                feats['dist_52w_high'] = np.nan
                feats['dist_52w_low'] = np.nan

            # Price relative to moving averages
            if idx >= 50:
                feats['price_to_ma50'] = price_now / np.mean(closes[idx - 50:idx + 1]) - 1.0
            else:
                feats['price_to_ma50'] = np.nan
            if idx >= 200:
                feats['price_to_ma200'] = price_now / np.mean(closes[idx - 200:idx + 1]) - 1.0
            else:
                feats['price_to_ma200'] = np.nan

            price_features.append(feats)

    if not price_features:
        return fund_df

    pf_df = pd.DataFrame(price_features)
    return fund_df.merge(pf_df, on='id', how='left')


PRICE_FEATURE_COLS = [
    'ret_1m', 'ret_3m', 'ret_6m', 'ret_1y',
    'vol_60d', 'dist_52w_high', 'dist_52w_low',
    'price_to_ma50', 'price_to_ma200',
]


def load_data():
    """
    Load and prepare train/test datasets with features and targets.

    Returns:
        train_df: DataFrame with features + 'peak_return_2y' column (snapshots < 2022)
        test_df:  DataFrame with features + 'peak_return_2y' column (snapshots 2022-2023)
        feature_cols: list of feature column names available for modeling

    The agent is free to engineer additional features from these columns,
    but must not use any future-looking information.
    """
    print("Loading data from database...")
    t0 = time.time()

    fund_df, price_df = _load_raw()
    print(f"  Loaded {len(fund_df)} snapshots, {len(price_df)} price rows in {time.time()-t0:.1f}s")

    print("Computing peak 2-year returns...")
    t1 = time.time()
    peak_rets = _compute_peak_returns(fund_df, price_df)
    fund_df['peak_return_2y'] = fund_df['id'].map(peak_rets)
    fund_df = fund_df.dropna(subset=['peak_return_2y'])
    print(f"  Computed {len(fund_df)} targets in {time.time()-t1:.1f}s")

    print("Adding price features...")
    t2 = time.time()
    fund_df = _add_price_features(fund_df, price_df)
    print(f"  Added price features in {time.time()-t2:.1f}s")

    feature_cols = FUNDAMENTAL_COLS + PRICE_FEATURE_COLS
    # Keep only columns that exist
    feature_cols = [c for c in feature_cols if c in fund_df.columns]

    # Split
    train_mask = fund_df['snapshot_date'] < TRAIN_CUTOFF
    test_mask = (fund_df['snapshot_date'] >= TRAIN_CUTOFF) & (fund_df['snapshot_date'] < TEST_END)

    train_df = fund_df[train_mask].copy().reset_index(drop=True)
    test_df = fund_df[test_mask].copy().reset_index(drop=True)

    print(f"  Train: {len(train_df)} samples | Test: {len(test_df)} samples")
    print(f"  Features: {len(feature_cols)} columns")
    print(f"  Target stats (train): median={train_df['peak_return_2y'].median():.2%}, "
          f"mean={train_df['peak_return_2y'].mean():.2%}")
    print(f"  Target stats (test):  median={test_df['peak_return_2y'].median():.2%}, "
          f"mean={test_df['peak_return_2y'].mean():.2%}")
    print(f"Data loading total: {time.time()-t0:.1f}s")

    return train_df, test_df, feature_cols


# ---------------------------------------------------------------------------
# Evaluation (DO NOT CHANGE — this is the fixed metric)
# ---------------------------------------------------------------------------

def score_predictions(actual, predicted):
    """
    Score predicted peak returns against actual peak returns.

    Primary metric: Spearman rank correlation (higher = better ranker).
    Secondary metrics for diagnostics only.

    Args:
        actual: array-like of actual peak 2-year returns
        predicted: array-like of predicted peak 2-year returns (same length)

    Returns:
        dict with metric names and values
    """
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    assert len(actual) == len(predicted), \
        f"Length mismatch: {len(actual)} actual vs {len(predicted)} predicted"

    # Remove NaN pairs
    mask = ~(np.isnan(actual) | np.isnan(predicted))
    actual = actual[mask]
    predicted = predicted[mask]
    n = len(actual)

    if n < 10:
        return {'spearman': 0.0, 'n_scored': n, 'error': 'too few valid predictions'}

    # Primary metric: Spearman rank correlation
    spearman_corr, spearman_p = spearmanr(actual, predicted)

    # Secondary: decile spread (top decile actual return - bottom decile actual return)
    deciles = pd.qcut(predicted, 10, labels=False, duplicates='drop')
    top_decile_actual = actual[deciles == deciles.max()].mean()
    bottom_decile_actual = actual[deciles == deciles.min()].mean()
    decile_spread = top_decile_actual - bottom_decile_actual

    # Secondary: top-decile mean actual return (are the ones you'd pick actually good?)
    top_decile_mean = top_decile_actual

    # Secondary: hit rate in top quintile (% of top-quintile picks that beat median)
    quintiles = pd.qcut(predicted, 5, labels=False, duplicates='drop')
    top_q = actual[quintiles == quintiles.max()]
    median_actual = np.median(actual)
    hit_rate_top_q = (top_q > median_actual).mean()

    return {
        'spearman': round(spearman_corr, 6),
        'spearman_p': round(spearman_p, 6),
        'decile_spread': round(decile_spread, 4),
        'top_decile_mean': round(top_decile_mean, 4),
        'hit_rate_top_q': round(hit_rate_top_q, 4),
        'n_scored': n,
    }


def print_results(results, training_seconds=None):
    """Print results in grep-friendly format (like Karpathy's output)."""
    print("---")
    print(f"spearman:         {results['spearman']:.6f}")
    print(f"decile_spread:    {results['decile_spread']:.4f}")
    print(f"top_decile_mean:  {results['top_decile_mean']:.4f}")
    print(f"hit_rate_top_q:   {results['hit_rate_top_q']:.4f}")
    print(f"n_scored:         {results['n_scored']}")
    if training_seconds is not None:
        print(f"training_seconds: {training_seconds:.1f}")


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    # Quick sanity check: random predictions
    train_df, test_df, feature_cols = load_data()
    random_preds = np.random.randn(len(test_df))
    results = score_predictions(test_df['peak_return_2y'].values, random_preds)
    print("\nRandom baseline:")
    print_results(results)
