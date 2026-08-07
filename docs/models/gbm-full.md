# GBM Models (1y / 3y)

Gradient boosting models predicting fixed-horizon stock returns using 464 engineered features. Displayed on the dashboard as **GBM 1y** and **GBM 3y**.

## Overview

The GBM models are the core fixed-horizon ranking models, using comprehensive feature engineering and 8+ quarters of historical data to predict 1-year and 3-year forward returns. They use LightGBM with cross-sectional normalization to learn relative stock attractiveness.

## Key Features

- **Strong Accuracy**: Rank IC 0.59-0.61
- **Rich Feature Set**: 464 features from 21 base metrics
- **Data Requirements**: 8+ quarters of history
- **Coverage**: ~52% of stocks (those with sufficient history)

## Available Variants

### GBM 1y
**Predicts 1-year forward returns**
- Rank IC: 0.59
- Decile Spread: 75%
- Top decile average return: 63%
- Bottom decile average return: -12%

### GBM 3y
**Predicts 3-year forward returns**
- Rank IC: 0.61
- Decile Spread: Not specified (but strong)
- Longer horizon allows mean reversion patterns

## Feature Engineering

### Base Features (21)
- **Fundamentals**: Profitability, growth, leverage, liquidity
- **Valuation**: PE, PB, PS, EV/EBITDA, EV/Revenue
- **Market**: VIX, Treasury rates
- **Price**: Returns, volatility, volume trends

### Engineered Features (~22x per base)

**1. Lag Features** (`[1, 2, 4, 8]` quarters):
- Captures historical values
- Enables momentum patterns
- Examples: `pe_ratio_lag1q`, `revenue_growth_lag4q`

**2. Change Features**:
- **QoQ**: Quarter-over-quarter deltas
- **YoY**: Year-over-year comparisons
- Example: `profit_margins_yoy`

**3. Rolling Statistics** (`[4, 8, 12]` quarter windows):
- **Mean**: Trend levels
- **Std**: Volatility/stability
- **Slope**: Direction/acceleration
- Example: `roe_mean8q`, `debt_to_equity_std12q`

**4. Missingness Flags**:
- Binary indicators for missing data
- Captures data quality signal

**5. Categorical**:
- Sector encoding (11 sectors)

### Total: 464 Features
```
21 base + (21 × 4 lags) + (21 × 2 changes) + (21 × 3 stats × 3 windows) + 21 flags + 11 sectors
= 21 + 84 + 42 + 189 + 21 + 11 = 368 + overheads ≈ 464
```

## Training Process

### Cross-Sectional Normalization
```python
# Per-date standardization
for date in unique_dates:
    features[date] = (features[date] - mean[date]) / std[date]
```

**Why:** Makes model regime-agnostic, focuses on relative rankings

### LightGBM Configuration
```python
params = {
    'objective': 'regression',
    'metric': 'rmse',
    'num_leaves': 31,
    'learning_rate': 0.05,
    'feature_fraction': 0.9,
    'bagging_fraction': 0.8,
    'bagging_freq': 5
}
```

### Time-Series Cross-Validation
- 5-fold expanding window
- No data leakage across folds
- Preserves temporal ordering

## Performance

| Metric | GBM 1y | GBM 3y |
|--------|--------|--------|
| Rank IC | 0.59 | 0.61 |
| Decile Spread | 75% | Strong |
| Features | 464 | 464 |
| Min Quarters | 8 | 8 |

!!! note "GBM Lite (retired)"
    A simplified 59-feature variant (GBM Lite) was previously available with only 2-quarter data requirements. It was removed from the dashboard for producing overoptimistic predictions. See [archived docs](gbm-lite.md).

## When to Use

### Best For
- **Maximum accuracy**: When you need the best possible rankings
- **Long-term holds**: Extra accuracy matters more
- **Established companies**: 8+ quarters available
- **Quantitative strategies**: Systematic portfolio construction

### Consider Other Models
- **Absolute valuation**: Use DCF/RIM instead of GBM
- **Peak return timing**: Use [GBM Opportunistic](gbm-opportunistic.md) or [AutoResearch](autoresearch.md)
- **Broader coverage**: AutoResearch covers more stocks with fewer data requirements

## Feature Importance

### Top Predictive Features (Typical)

1. **Price Momentum** (15-20% importance)
   - returns_3m, returns_6m, returns_1y
   - Strongest short-term signal

2. **Valuation Changes** (12-18%)
   - pe_ratio_qoq, pb_ratio_yoy
   - Direction of cheapening/expensive

3. **Profitability Trends** (10-15%)
   - profit_margins_slope4q, roe_mean8q
   - Quality improvement/deterioration

4. **Growth Acceleration** (10-12%)
   - revenue_growth_qoq, earnings_growth_slope
   - Second derivative matters

5. **Volatility** (8-10%)
   - volatility, roe_std8q
   - Risk-adjusted returns

## Implementation

```python
from invest.scripts.run_gbm_predictions import run_predictions

# Run GBM Full 1y
predictions = run_predictions(
    variant='standard',  # 'standard' = full model
    horizon='1y',
    db_path='data/stock_data.db'
)

# Get top quintile
top_20pct = predictions[predictions['percentile'] >= 80]
```

## Theoretical Foundation

### Why Historical Depth Matters

**Mean Reversion Patterns:**
- High ROE tends to fade (rolling avg captures this)
- Low margins tend to improve (slope detects acceleration)
- Extremes revert to sector norms (std flags outliers)

**Momentum Persistence:**
- 6-12 month price momentum predicts next 3-12 months
- Fundamental momentum (growth acceleration) also persists
- Lags capture these patterns

**Volatility Regimes:**
- High volatility stocks underperform (risk penalty)
- Volatility of fundamentals signals instability
- Rolling std quantifies this

### Cross-Sectional Learning

GBM learns **relative** attractiveness:
- Ranking objective, not absolute returns
- Per-date normalization removes market timing
- Focus on stock selection within universe

## Academic References

### Gradient Boosting
- Friedman, J. H. (2001). "Greedy Function Approximation: A Gradient Boosting Machine". *Annals of Statistics*.
- Chen, T., & Guestrin, C. (2016). "XGBoost: A Scalable Tree Boosting System". *KDD*.
- Ke, G., et al. (2017). "LightGBM: A Highly Efficient Gradient Boosting Decision Tree". *NIPS*.

### Factor Models & ML
- Gu, S., Kelly, B., & Xiu, D. (2020). "Empirical Asset Pricing via Machine Learning". *Review of Financial Studies*.
- Moritz, B., & Zimmermann, T. (2016). "Tree-Based Conditional Portfolio Sorts". *Working Paper*.
- Kozak, S., Nagel, S., & Santosh, S. (2020). "Shrinking the Cross-Section". *Journal of Financial Economics*.

### Feature Engineering
- Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and Selling Losers". *Journal of Finance*.
- Fama, E., & French, K. (2015). "A Five-Factor Asset Pricing Model". *Journal of Financial Economics*.

## Related Models

- **[AutoResearch](autoresearch.md)**: 5-model ensemble for peak 2-year return prediction
- **[GBM Opportunistic](gbm-opportunistic.md)**: Peak return prediction variant (1y and 3y)
- **[DCF](dcf.md)**: Absolute valuation alternative
- **[RIM](rim.md)**: Residual income valuation for financials
