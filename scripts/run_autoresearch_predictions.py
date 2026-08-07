#!/usr/bin/env python3
"""
Run autoresearch ensemble predictions and save to valuation_results.

Uses the 5-model rank ensemble from models/autoresearch/train.py to predict
peak 2-year returns for all stocks with fundamental history.

Usage:
    uv run python scripts/run_autoresearch_predictions.py
"""

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2.extras

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / 'models' / 'autoresearch'))

from invest.data.db import get_connection, get_engine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_NAME = 'autoresearch'


def load_training_data():
    """Load all fundamental_history as training data (same as evaluate.py)."""
    engine = get_engine()

    fund_df = pd.read_sql_query("""
        SELECT f.*, a.symbol as ticker, a.sector, a.industry
        FROM fundamental_history f
        JOIN assets a ON f.asset_id = a.id
        WHERE f.vix IS NOT NULL
        ORDER BY a.symbol, f.snapshot_date
    """, engine)
    fund_df['snapshot_date'] = pd.to_datetime(fund_df['snapshot_date'])

    price_df = pd.read_sql_query("""
        SELECT ticker, date, close
        FROM price_history
        WHERE close IS NOT NULL
        ORDER BY ticker, date
    """, engine)
    price_df['date'] = pd.to_datetime(price_df['date'])

    return fund_df, price_df


def compute_peak_returns(fund_df, price_df, forward_days=504):
    """Compute peak return in 2-year forward window for training targets."""
    peak_returns = {}
    for ticker, group in price_df.groupby('ticker'):
        group = group.sort_values('date').reset_index(drop=True)
        closes = group['close'].values
        dates = group['date'].values

        ticker_snapshots = fund_df[fund_df['ticker'] == ticker]
        for _, row in ticker_snapshots.iterrows():
            snap_date = row['snapshot_date']
            idx = np.searchsorted(dates, snap_date)
            if idx >= len(dates):
                continue
            baseline = closes[idx]
            if baseline <= 0:
                continue
            end_idx = min(idx + forward_days, len(closes))
            if end_idx - idx < 63:
                continue
            peak = closes[idx:end_idx].max()
            peak_returns[row['id']] = (peak / baseline) - 1.0

    return peak_returns


def add_price_features(fund_df, price_df):
    """Add momentum/technical features from price history."""
    price_features = []
    for ticker, group in price_df.groupby('ticker'):
        group = group.sort_values('date').reset_index(drop=True)
        closes = group['close'].values
        dates = group['date'].values

        ticker_snapshots = fund_df[fund_df['ticker'] == ticker]
        for _, row in ticker_snapshots.iterrows():
            snap_date = row['snapshot_date']
            idx = np.searchsorted(dates, snap_date)
            if idx < 21:
                continue
            price_now = closes[min(idx, len(closes) - 1)]
            if price_now <= 0:
                continue

            feats = {'id': row['id']}
            for name, lb in [('ret_1m', 21), ('ret_3m', 63), ('ret_6m', 126), ('ret_1y', 252)]:
                feats[name] = (price_now / closes[idx - lb]) - 1.0 if idx >= lb else np.nan

            start = max(0, idx - 60)
            window = closes[start:idx + 1]
            daily_rets = np.diff(window) / window[:-1]
            feats['vol_60d'] = np.std(daily_rets) * np.sqrt(252) if len(daily_rets) > 5 else np.nan

            if idx >= 252:
                hi = closes[idx - 252:idx + 1].max()
                lo = closes[idx - 252:idx + 1].min()
                feats['dist_52w_high'] = (price_now / hi) - 1.0
                feats['dist_52w_low'] = (price_now / lo) - 1.0
            else:
                feats['dist_52w_high'] = feats['dist_52w_low'] = np.nan

            feats['price_to_ma50'] = (price_now / np.mean(closes[idx - 50:idx + 1]) - 1.0) if idx >= 50 else np.nan
            feats['price_to_ma200'] = (price_now / np.mean(closes[idx - 200:idx + 1]) - 1.0) if idx >= 200 else np.nan
            price_features.append(feats)

    if price_features:
        pf_df = pd.DataFrame(price_features)
        fund_df = fund_df.merge(pf_df, on='id', how='left')
    return fund_df


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

PRICE_FEATURE_COLS = [
    'ret_1m', 'ret_3m', 'ret_6m', 'ret_1y',
    'vol_60d', 'dist_52w_high', 'dist_52w_low',
    'price_to_ma50', 'price_to_ma200',
]


def engineer_features(df, feature_cols):
    """Feature engineering — same as models/autoresearch/train.py."""
    X = df[feature_cols].copy()
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors='coerce')

    for col in ['market_cap', 'volume', 'total_cash', 'total_debt',
                'operating_cashflow', 'free_cashflow', 'shares_outstanding']:
        if col in X.columns:
            vals = pd.to_numeric(X[col], errors='coerce').clip(lower=0)
            X[f'log_{col}'] = np.log1p(vals)

    if 'free_cashflow' in X.columns and 'market_cap' in X.columns:
        fcf = pd.to_numeric(X['free_cashflow'], errors='coerce')
        mc = pd.to_numeric(X['market_cap'], errors='coerce')
        X['fcf_yield'] = fcf / (mc + 1e9)
    if 'operating_cashflow' in X.columns and 'market_cap' in X.columns:
        ocf = pd.to_numeric(X['operating_cashflow'], errors='coerce')
        mc = pd.to_numeric(X['market_cap'], errors='coerce')
        X['ocf_yield'] = ocf / (mc + 1e9)
    if 'trailing_eps' in X.columns and 'book_value' in X.columns:
        eps = pd.to_numeric(X['trailing_eps'], errors='coerce')
        bv = pd.to_numeric(X['book_value'], errors='coerce')
        X['earnings_yield'] = eps / (bv.abs() + 1e-6)

    if 'total_debt' in X.columns and 'total_cash' in X.columns:
        debt = pd.to_numeric(X['total_debt'], errors='coerce')
        cash = pd.to_numeric(X['total_cash'], errors='coerce')
        X['net_debt'] = debt - cash
        if 'market_cap' in X.columns:
            mc = pd.to_numeric(X['market_cap'], errors='coerce')
            X['net_debt_to_mcap'] = (debt - cash) / (mc + 1e9)

    mom_cols = ['ret_1m', 'ret_3m', 'ret_6m', 'ret_1y']
    existing_mom = [c for c in mom_cols if c in X.columns]
    if len(existing_mom) >= 2:
        X['momentum_composite'] = X[existing_mom].mean(axis=1)
        if 'ret_1m' in X.columns and 'ret_1y' in X.columns:
            X['momentum_reversal'] = X['ret_1m'] - X['ret_1y']

    val_cols = ['pe_ratio', 'pb_ratio', 'ps_ratio', 'enterprise_to_ebitda']
    existing_val = [c for c in val_cols if c in X.columns]
    if len(existing_val) >= 2:
        for vc in existing_val:
            X[f'{vc}_rank'] = X[vc].rank(pct=True)
        X['valuation_rank_avg'] = X[[f'{vc}_rank' for vc in existing_val]].mean(axis=1)

    quality_cols = ['return_on_equity', 'return_on_assets', 'profit_margins', 'operating_margins']
    existing_q = [c for c in quality_cols if c in X.columns]
    if len(existing_q) >= 2:
        for qc in existing_q:
            X[f'{qc}_rank'] = X[qc].rank(pct=True)
        X['quality_rank_avg'] = X[[f'{qc}_rank' for qc in existing_q]].mean(axis=1)

    if 'revenue_growth' in X.columns and 'earnings_growth' in X.columns:
        rg = pd.to_numeric(X['revenue_growth'], errors='coerce')
        eg = pd.to_numeric(X['earnings_growth'], errors='coerce')
        X['growth_composite'] = (rg + eg) / 2

    if 'ret_6m' in X.columns and 'vol_60d' in X.columns:
        X['sharpe_6m'] = X['ret_6m'] / (X['vol_60d'] + 1e-6)

    if 'dist_52w_high' in X.columns and 'vol_60d' in X.columns:
        X['dist_high_vol_ratio'] = X['dist_52w_high'] / (X['vol_60d'] + 1e-6)

    if 'vix' in X.columns and 'dist_52w_high' in X.columns:
        vix = X['vix'].values.astype(float)
        X['vix_x_dist_high'] = vix * X['dist_52w_high'].values

    return X


def train_and_predict(train_df, predict_df, feature_cols):
    """Train 5-model ensemble on all historical data, predict on latest snapshots."""
    import lightgbm as lgb
    from catboost import CatBoostRegressor
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import BaggingRegressor
    from sklearn.tree import DecisionTreeRegressor
    from scipy.stats import rankdata

    X_train = engineer_features(train_df, feature_cols)
    X_predict = engineer_features(predict_df, feature_cols)
    y_train = train_df['peak_return_2y'].values

    # Winsorize + log transform target
    cap_hi = np.percentile(y_train, 95)
    cap_lo = np.percentile(y_train, 5)
    y_train_w = np.clip(y_train, cap_lo, cap_hi)
    y_train_log = np.log1p(y_train_w)

    logger.info(f'Training on {len(X_train)} samples, predicting {len(X_predict)} stocks')

    # 1. LightGBM DART
    lgb_params = {
        'objective': 'regression', 'metric': 'mae', 'boosting_type': 'dart',
        'learning_rate': 0.05, 'num_leaves': 127, 'max_depth': 10,
        'min_child_samples': 30, 'subsample': 0.8, 'colsample_bytree': 0.7,
        'reg_alpha': 0.1, 'reg_lambda': 1.0, 'drop_rate': 0.1,
        'verbose': -1, 'n_jobs': -1, 'seed': 42,
    }
    lgb_model = lgb.train(lgb_params, lgb.Dataset(X_train, label=y_train_log), num_boost_round=500)
    lgb_preds = lgb_model.predict(X_predict)
    logger.info('LightGBM DART done')

    # 2. CatBoost
    cb_model = CatBoostRegressor(
        iterations=1500, learning_rate=0.02, depth=8, l2_leaf_reg=5.0,
        subsample=0.8, colsample_bylevel=0.7, random_seed=42, verbose=0,
        loss_function='MAE',
    )
    cb_model.fit(X_train.values, y_train_log)
    cb_preds = cb_model.predict(X_predict.values)
    logger.info('CatBoost done')

    # Fill NaN for sklearn models
    X_tr_filled = X_train.fillna(-999)
    X_pr_filled = X_predict.fillna(-999)

    # 3. KNN k=15
    scaler = StandardScaler()
    X_tr_knn = scaler.fit_transform(np.nan_to_num(X_tr_filled.values, nan=0.0))
    X_pr_knn = scaler.transform(np.nan_to_num(X_pr_filled.values, nan=0.0))
    knn1 = KNeighborsRegressor(n_neighbors=15, weights='distance', n_jobs=-1)
    knn1.fit(X_tr_knn, y_train_log)
    knn1_preds = knn1.predict(X_pr_knn)
    logger.info('KNN k=15 done')

    # 4. KNN k=100
    knn2 = KNeighborsRegressor(n_neighbors=100, weights='uniform', n_jobs=-1)
    knn2.fit(X_tr_knn, y_train_log)
    knn2_preds = knn2.predict(X_pr_knn)
    logger.info('KNN k=100 done')

    # 5. BaggingRegressor
    bag = BaggingRegressor(
        estimator=DecisionTreeRegressor(max_depth=12, min_samples_leaf=20),
        n_estimators=500, max_samples=0.8, max_features=0.7,
        random_state=42, n_jobs=-1,
    )
    bag.fit(X_tr_filled.values, y_train_log)
    bag_preds = bag.predict(X_pr_filled.values)
    logger.info('BaggingRegressor done')

    # Rank-based blend
    r1 = rankdata(lgb_preds)
    r2 = rankdata(cb_preds)
    r3 = rankdata(knn1_preds)
    r4 = rankdata(knn2_preds)
    r5 = rankdata(bag_preds)
    rank_blend = (r1 + r2 + r3 + r4 + r5) / 5.0

    # Convert rank blend to predicted return (use average of log-space predictions)
    avg_log_pred = (lgb_preds + cb_preds + knn1_preds + knn2_preds + bag_preds) / 5.0
    predicted_returns = np.expm1(avg_log_pred)  # reverse log1p

    # Confidence from rank percentile (0.5-1.0)
    confidences = 0.5 + 0.5 * (rank_blend - rank_blend.min()) / (rank_blend.max() - rank_blend.min())

    return predicted_returns, confidences


def save_predictions(predict_df, predicted_returns, confidences):
    """Save predictions to valuation_results table."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM valuation_results WHERE model_name = %s", (MODEL_NAME,))
    logger.info(f'Deleted {cursor.rowcount} existing {MODEL_NAME} predictions')

    # One query for all current prices (was: StockDataReader.get_stock_data per
    # ticker, which opens ~7 connections/ticker over the SSH tunnel — ~42 min to
    # save ~760 rows), plus a single batched INSERT instead of one per row.
    tickers = [str(t) for t in predict_df['ticker'].tolist()]
    cursor.execute(
        "SELECT ticker, current_price FROM current_stock_data WHERE ticker = ANY(%s)",
        (tickers,),
    )
    price_map = {r[0]: r[1] for r in cursor.fetchall()}

    rows = []
    skipped = 0
    for i, (_, row) in enumerate(predict_df.iterrows()):
        ticker = row['ticker']
        current_price = price_map.get(ticker)
        if not current_price or float(current_price) == 0:
            skipped += 1
            continue

        current_price = float(current_price)
        predicted_return = float(predicted_returns[i])
        fair_value = current_price * (1 + predicted_return)
        upside_pct = predicted_return * 100
        margin_of_safety = predicted_return

        details = {
            'predicted_peak_return_2y': round(predicted_return, 4),
            'ranking_percentile': round(float(confidences[i]) * 100, 1),
            'model': '5-model rank ensemble (LGB DART + CatBoost + KNN15 + KNN100 + BaggingDT)',
        }

        rows.append((
            ticker, MODEL_NAME, float(fair_value), current_price,
            float(margin_of_safety), float(upside_pct), True,
            float(confidences[i]), json.dumps(details),
        ))

    psycopg2.extras.execute_values(
        cursor,
        '''
        INSERT INTO valuation_results
        (ticker, model_name, fair_value, current_price, margin_of_safety,
         upside_pct, suitable, confidence, details_json)
        VALUES %s
        ''',
        rows,
    )

    conn.commit()
    conn.close()
    logger.info(f'Inserted {len(rows)} {MODEL_NAME} predictions (skipped {skipped})')


def main():
    logger.info('=== Autoresearch Predictions ===')

    # Load all data
    logger.info('Loading data...')
    fund_df, price_df = load_training_data()
    logger.info(f'Loaded {len(fund_df)} snapshots, {len(price_df)} price rows')

    # Compute targets for training
    logger.info('Computing peak 2y return targets...')
    peak_rets = compute_peak_returns(fund_df, price_df)
    fund_df['peak_return_2y'] = fund_df['id'].map(peak_rets)

    # Add price features
    logger.info('Adding price features...')
    fund_df = add_price_features(fund_df, price_df)

    feature_cols = [c for c in FUNDAMENTAL_COLS + PRICE_FEATURE_COLS if c in fund_df.columns]

    # Training set: all snapshots with targets
    train_df = fund_df.dropna(subset=['peak_return_2y']).reset_index(drop=True)
    logger.info(f'Training samples with targets: {len(train_df)}')

    # Prediction set: latest snapshot per ticker
    latest_df = fund_df.loc[fund_df.groupby('ticker')['snapshot_date'].idxmax()].reset_index(drop=True)
    logger.info(f'Predicting for {len(latest_df)} tickers')

    # Train and predict
    predicted_returns, confidences = train_and_predict(train_df, latest_df, feature_cols)

    # Save to database
    save_predictions(latest_df, predicted_returns, confidences)
    logger.info('Done!')


if __name__ == '__main__':
    main()
