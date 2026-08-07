# GBM Lite Models (Retired)

!!! warning "Retired Model"
    GBM Lite has been removed from the dashboard as of March 2026 due to overoptimistic predictions. This page is kept for reference. See [active models](index.md).

Ultra-lightweight gradient boosting models optimized for maximum stock coverage with minimal data requirements.

## Overview

GBM Lite models use machine learning to rank stocks by expected returns while requiring only **2 quarters of historical data** - enabling predictions for ~98% of stocks in the database.

## Key Features

- **Minimal Data Requirements**: Only 2 quarters needed (vs 8+ for full GBM)
- **Maximum Coverage**: Works for 589/598 stocks (98.5%)
- **Strong Performance**: Rank IC 0.50 (1y) and 0.40 (3y)
- **Efficient**: 59 features (vs 464 for full GBM)

## Available Variants

### GBM Lite 1y
Predicts 1-year forward returns.

- **Rank IC**: 0.50
- **Decile Spread**: 66%
- **Coverage**: 589 stocks

### GBM Lite 3y
Predicts 3-year forward returns.

- **Rank IC**: 0.40
- **Decile Spread**: 145%
- **Coverage**: 589 stocks

## How It Works

### 1. Feature Engineering

The model uses 59 engineered features derived from:

**Current Snapshot (27 base features)**:
- Profitability: profit_margins, operating_margins, gross_margins, ROE, ROA
- Growth: revenue_growth, earnings_growth
- Balance Sheet: debt_to_equity, current_ratio, quick_ratio
- Valuation: PE, PB, PS, EV/EBITDA, EV/Revenue
- Dividends: dividend_yield, payout_ratio
- Company: market_cap, beta
- Market: VIX, 10Y Treasury
- Price Momentum: returns_1m, returns_3m, returns_6m, returns_1y, volatility, volume_trend

**Engineered Features** (2.2x per base feature):
- Computed yields: FCF yield, OCF yield, earnings yield
- Log transforms: log(market_cap)
- **QoQ changes**: Quarter-over-quarter deltas
- Missingness flags: Binary indicators for missing data
- Categorical: Sector encoding

### 2. What's Excluded (vs Full GBM)

To achieve 2-quarter minimum, we removed:

- ❌ **Lag features** (would require 3+ quarters)
- ❌ **Rolling windows** (would require 4-6+ quarters)
- ❌ **YoY changes** (would require 5 quarters)

### 3. Training Process

```python
# Cross-sectional normalization
features_normalized = winsorize(features, 1st-99th percentile)
features_normalized = standardize(features, by_date=True)

# LightGBM ranking objective
model = lgb.train(
    params={'objective': 'regression', 'metric': 'rmse'},
    train_data=train_set,
    num_boost_round=500,
    early_stopping_rounds=50
)
```

### 4. Prediction Output

For each stock, the model provides:

- **Expected Return**: Predicted percentage return over horizon
- **Percentile Rank**: 0-100 ranking vs all stocks
- **Decile**: 1-10 grouping (10 = top 10% expected returns)

## Performance Metrics

### Rank Information Coefficient (IC)

Measures correlation between predicted ranks and actual returns:

- **GBM Lite 1y**: 0.50 (strong predictive power)
- **GBM Lite 3y**: 0.40 (good long-term signal)

### Decile Spread

Average return difference between top and bottom deciles:

- **GBM Lite 1y**: 66% (top 10% outperform bottom 10% by 66%)
- **GBM Lite 3y**: 145% (massive 3-year spread)

### Comparison to Full GBM

| Metric | GBM Lite 1y | GBM Full 1y | Delta |
|--------|-------------|-------------|-------|
| Rank IC | 0.50 | 0.59 | -15% |
| Decile Spread | 66% | 75% | -12% |
| Features | 59 | 464 | -87% |
| Coverage | 589 stocks | 589 stocks | Same |
| Min Quarters | 2 | 8 | -75% |

**Key Insight**: GBM Lite achieves 85-88% of full GBM's performance while covering the same stocks with 76% fewer features.

## Theoretical Foundation

### Cross-Sectional Learning

GBM models learn **relative** patterns, not absolute values:

1. **Z-score normalization per date**: All features standardized within each time period
2. **Ranking objective**: Model predicts relative ordering, not exact returns
3. **Regime-agnostic**: Works across market conditions by focusing on cross-sectional relationships

### Why It Works with Minimal History

**Current snapshot + momentum captures most signal**:
- Fundamental quality metrics (profitability, growth, leverage)
- Valuation multiples (relative cheapness)
- Recent price momentum (trend signals)
- QoQ changes (acceleration/deceleration)

**What historical depth adds** (full GBM):
- Mean reversion patterns (rolling averages)
- Volatility trends (rolling std)
- Long-term momentum (lags, slopes)

For stock ranking, current state + recent changes provide most discriminating power.

## Use Cases

### Best For

- **New listings**: Stocks with limited trading history
- **Broad coverage**: When you need predictions for almost all stocks
- **Resource efficiency**: Fast training and prediction
- **Baseline model**: Good starting point before adding complexity

### Not Ideal For

- **Absolute return forecasts**: Use LSTM models instead
- **Maximum accuracy**: Use full GBM if you have 8+ quarters
- **Market timing**: Use Opportunistic GBM instead

## Implementation Example

```python
from invest.scripts.run_gbm_predictions import run_predictions

# Run GBM Lite 1y predictions
predictions = run_predictions(
    variant='lite',
    horizon='1y',
    db_path='data/stock_data.db'
)

# Get top decile stocks
top_stocks = predictions[predictions['decile'] >= 9]
print(f"Top 20% stocks: {len(top_stocks)}")
```

## References

- [GBM Full Models](gbm-full.md) - For comparison with full-featured version
- [Training Script](https://github.com/rubenayla/invest-engine/blob/main/models/neural_network/training/train_gbm_lite_stock_ranker.py)
- [Feature Configuration](https://github.com/rubenayla/invest-engine/blob/main/models/neural_network/training/gbm_lite_feature_config.py)
- [Prediction Script](https://github.com/rubenayla/invest-engine/blob/main/scripts/run_gbm_predictions.py)

## Academic Background

### Gradient Boosting Machines
- Chen & Guestrin (2016). "XGBoost: A Scalable Tree Boosting System". KDD '16
- Ke et al. (2017). "LightGBM: A Highly Efficient Gradient Boosting Decision Tree". NIPS '17

### Factor Models & Cross-Sectional Prediction
- Fama & French (1993). "Common risk factors in the returns on stocks and bonds"
- Gu, Kelly, & Xiu (2020). "Empirical Asset Pricing via Machine Learning". Review of Financial Studies
- Moritz & Zimmermann (2016). "Tree-based Conditional Portfolio Sorts"

### Information Coefficient
- Grinold & Kahn (2000). "Active Portfolio Management" (Information Ratio framework)
