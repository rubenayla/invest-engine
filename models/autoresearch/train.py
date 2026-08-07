"""
Stock return prediction model — the file the agent modifies.

Predicts: approximate maximum expected return in a 2-year forward window.
Metric: Spearman rank correlation (higher is better).
Time budget: 120 seconds for training + prediction.

Everything is fair game: model choice, features, architecture, hyperparameters.
The only constraint: use load_data() for data, score_predictions() for scoring.
"""

import time
from pathlib import Path
import numpy as np
import pandas as pd
import lightgbm as lgb
from catboost import CatBoostRegressor
from evaluate import load_data, score_predictions, print_results, TIME_BUDGET

# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def engineer_features(df, feature_cols):
    """Build feature matrix from raw data. Modify freely."""
    X = df[feature_cols].copy()
    for col in X.columns:
        X[col] = pd.to_numeric(X[col], errors='coerce')

    # Log-transform skewed features
    for col in ['market_cap', 'volume', 'total_cash', 'total_debt',
                'operating_cashflow', 'free_cashflow', 'shares_outstanding']:
        if col in X.columns:
            vals = pd.to_numeric(X[col], errors='coerce').clip(lower=0)
            X[f'log_{col}'] = np.log1p(vals)

    # Derived ratios
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

    # Debt-related ratios
    if 'total_debt' in X.columns and 'total_cash' in X.columns:
        debt = pd.to_numeric(X['total_debt'], errors='coerce')
        cash = pd.to_numeric(X['total_cash'], errors='coerce')
        X['net_debt'] = debt - cash
        if 'market_cap' in X.columns:
            mc = pd.to_numeric(X['market_cap'], errors='coerce')
            X['net_debt_to_mcap'] = (debt - cash) / (mc + 1e9)

    # Momentum composite
    mom_cols = ['ret_1m', 'ret_3m', 'ret_6m', 'ret_1y']
    existing_mom = [c for c in mom_cols if c in X.columns]
    if len(existing_mom) >= 2:
        X['momentum_composite'] = X[existing_mom].mean(axis=1)
        if 'ret_1m' in X.columns and 'ret_1y' in X.columns:
            X['momentum_reversal'] = X['ret_1m'] - X['ret_1y']

    # Valuation composite (rank-based)
    val_cols = ['pe_ratio', 'pb_ratio', 'ps_ratio', 'enterprise_to_ebitda']
    existing_val = [c for c in val_cols if c in X.columns]
    if len(existing_val) >= 2:
        for vc in existing_val:
            X[f'{vc}_rank'] = X[vc].rank(pct=True)
        rank_cols = [f'{vc}_rank' for vc in existing_val]
        X['valuation_rank_avg'] = X[rank_cols].mean(axis=1)

    # Quality composite
    quality_cols = ['return_on_equity', 'return_on_assets', 'profit_margins', 'operating_margins']
    existing_q = [c for c in quality_cols if c in X.columns]
    if len(existing_q) >= 2:
        for qc in existing_q:
            X[f'{qc}_rank'] = X[qc].rank(pct=True)
        qrank_cols = [f'{qc}_rank' for qc in existing_q]
        X['quality_rank_avg'] = X[qrank_cols].mean(axis=1)

    # Growth features
    if 'revenue_growth' in X.columns and 'earnings_growth' in X.columns:
        rg = pd.to_numeric(X['revenue_growth'], errors='coerce')
        eg = pd.to_numeric(X['earnings_growth'], errors='coerce')
        X['growth_composite'] = (rg + eg) / 2

    # Volatility-adjusted momentum
    if 'ret_6m' in X.columns and 'vol_60d' in X.columns:
        X['sharpe_6m'] = X['ret_6m'] / (X['vol_60d'] + 1e-6)

    # Distance from 52w high as pct (interaction)
    if 'dist_52w_high' in X.columns and 'vol_60d' in X.columns:
        X['dist_high_vol_ratio'] = X['dist_52w_high'] / (X['vol_60d'] + 1e-6)

    # VIX x drawdown interaction (fear + value = opportunity)
    if 'vix' in X.columns and 'dist_52w_high' in X.columns:
        vix = X['vix'].values.astype(float)
        X['vix_x_dist_high'] = vix * X['dist_52w_high'].values

    return X


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def train_and_predict(train_df, test_df, feature_cols):
    """Train LightGBM + CatBoost ensemble, return blended predictions."""

    X_train = engineer_features(train_df, feature_cols)
    X_test = engineer_features(test_df, feature_cols)
    y_train = train_df['peak_return_2y'].values

    # Winsorize extreme targets (cap at 5th and 95th percentile)
    cap_hi = np.percentile(y_train, 95)
    cap_lo = np.percentile(y_train, 5)
    y_train_w = np.clip(y_train, cap_lo, cap_hi)

    # Log-transform target
    y_train_log = np.log1p(y_train_w)

    # --- LightGBM DART ---
    lgb_params = {
        'objective': 'regression',
        'metric': 'mae',
        'boosting_type': 'dart',
        'learning_rate': 0.05,
        'num_leaves': 127,
        'max_depth': 10,
        'min_child_samples': 30,
        'subsample': 0.8,
        'colsample_bytree': 0.7,
        'reg_alpha': 0.1,
        'reg_lambda': 1.0,
        'drop_rate': 0.1,
        'verbose': -1,
        'n_jobs': -1,
        'seed': 42,
    }
    train_data = lgb.Dataset(X_train, label=y_train_log)
    lgb_model = lgb.train(lgb_params, train_data, num_boost_round=500)
    lgb_preds = lgb_model.predict(X_test)

    # --- CatBoost ---
    cb_model = CatBoostRegressor(
        iterations=1500,
        learning_rate=0.02,
        depth=8,
        l2_leaf_reg=5.0,
        subsample=0.8,
        colsample_bylevel=0.7,
        random_seed=42,
        verbose=0,
        loss_function='MAE',
        train_dir=str(Path(__file__).resolve().parent / 'catboost_info'),
    )
    cb_model.fit(X_train.values, y_train_log)
    cb_preds = cb_model.predict(X_test.values)

    # Fill NaN for sklearn
    X_tr_filled = X_train.fillna(-999)
    X_te_filled = X_test.fillna(-999)

    # --- KNN Regressor (local similarity, diverse from tree methods) ---
    from sklearn.neighbors import KNeighborsRegressor
    from sklearn.preprocessing import StandardScaler
    knn_scaler = StandardScaler()
    X_tr_knn = knn_scaler.fit_transform(np.nan_to_num(X_tr_filled.values, nan=0.0))
    X_te_knn = knn_scaler.transform(np.nan_to_num(X_te_filled.values, nan=0.0))
    knn_model = KNeighborsRegressor(n_neighbors=15, weights='distance', n_jobs=-1)
    knn_model.fit(X_tr_knn, y_train_log)
    knn_preds = knn_model.predict(X_te_knn)

    # --- KNN 2 (broader neighborhood, k=100) ---
    knn_model2 = KNeighborsRegressor(n_neighbors=100, weights='uniform', n_jobs=-1)
    knn_model2.fit(X_tr_knn, y_train_log)
    knn2_preds = knn_model2.predict(X_te_knn)

    # --- BaggingRegressor (for diversity from boosters) ---
    from sklearn.ensemble import BaggingRegressor
    from sklearn.tree import DecisionTreeRegressor
    bag_model = BaggingRegressor(
        estimator=DecisionTreeRegressor(max_depth=12, min_samples_leaf=20),
        n_estimators=500,
        max_samples=0.8,
        max_features=0.7,
        random_state=42,
        n_jobs=-1,
    )
    bag_model.fit(X_tr_filled.values, y_train_log)
    hgb_preds = bag_model.predict(X_te_filled.values)

    # Rank-based blend of five (LGB + CB + KNN15 + KNN100 + HGB)
    from scipy.stats import rankdata
    r1 = rankdata(lgb_preds)
    r2 = rankdata(cb_preds)
    r3 = rankdata(knn_preds)
    r3b = rankdata(knn2_preds)
    r4 = rankdata(hgb_preds)
    predictions = (r1 + r2 + r3 + r3b + r4) / 5.0

    return predictions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    train_df, test_df, feature_cols = load_data()

    print("\nTraining model...")
    t0 = time.time()
    predictions = train_and_predict(train_df, test_df, feature_cols)
    training_seconds = time.time() - t0
    print(f"Training + prediction: {training_seconds:.1f}s")

    if training_seconds > TIME_BUDGET:
        print(f"WARNING: exceeded time budget ({TIME_BUDGET}s)")

    results = score_predictions(test_df['peak_return_2y'].values, predictions)
    print_results(results, training_seconds=training_seconds)
