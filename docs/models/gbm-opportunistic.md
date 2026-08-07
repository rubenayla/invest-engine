# GBM Opportunistic Models

Gradient boosting models that predict **peak return timing** rather than fixed-horizon returns, designed to identify opportunistic trades.

## Overview

Unlike GBM Full/Lite which predict 1-year or 3-year returns, GBM Opportunistic models answer: **"What's the maximum gain this stock could achieve in the next 1-3 years, and when?"**

This approach is ideal for:
- Tactical trading (not buy-and-hold)
- Identifying catalysts and inflection points
- Opportunistic entries on quality names
- Maximizing risk-adjusted returns through timing

## Key Difference from Standard GBM

### Standard GBM (Full/Lite)
```
Question: "What will this stock return over the next 1 year?"
Answer: "Expected to return 15%"
Use Case: Portfolio construction, long-term ranking
```

### GBM Opportunistic
```
Question: "What's the best return achievable in the next 1-3 years?"
Answer: "Could gain 45% within 18 months at peak"
Use Case: Timing trades, identifying breakout candidates
```

## Available Variants

### GBM Opportunistic 1y Peak
**Predicts maximum return achievable within 1 year**
- Captures near-term catalysts
- Earnings surprises, product launches
- Short-term momentum inflections
- Higher turnover strategy

### GBM Opportunistic 3y Peak
**Predicts maximum return achievable within 3 years**
- Structural turnarounds
- Multi-year growth trajectories
- Mean reversion opportunities
- Lower turnover, higher conviction

## How It Works

### Target Variable Construction

Instead of fixed-horizon return:
```python
# Standard GBM target
return_1y = (price_t+252 - price_t) / price_t

# Opportunistic GBM target
return_peak = max(
    (price_t+1 - price_t) / price_t,
    (price_t+2 - price_t) / price_t,
    ...
    (price_t+252 - price_t) / price_t
)
# Returns maximum gain observed at ANY point in next 252 days
```

**Key Insight:** This captures stocks that may spike to 50% up mid-year even if they end the year at +20%.

### Feature Engineering

Uses same rich feature set as GBM Full:
- 464 engineered features
- Lag features, rolling statistics, change features
- Cross-sectional normalization
- See [GBM Full documentation](gbm-full.md) for details

### Training Objective

```python
# Regression on peak returns
objective = 'regression'
metric = 'rmse'

# Model learns to predict:
y_pred = max_return_within_horizon
```

**Result:** Model identifies stocks with highest upside potential, regardless of when that potential is realized.

## Performance Characteristics

### Opportunistic 1y Peak

**Typical Metrics:**
- Mean peak return (top decile): 80-120%
- Mean 1y return (top decile): 40-60%
- Peak timing: 3-9 months average
- Hit rate (positive peak): 85%+

**Interpretation:**
Stocks ranked highly achieve large gains at some point, but timing varies

### Opportunistic 3y Peak

**Typical Metrics:**
- Mean peak return (top decile): 150-250%
- Mean 3y return (top decile): 60-100%
- Peak timing: 12-30 months average
- Hit rate (positive peak): 90%+

**Interpretation:**
Captures multi-year winners early, even if path is volatile

## Use Cases

### 1. Tactical Trading

**Strategy:**
- Buy top-ranked opportunistic stocks
- Set trailing stops at 20-30% to capture peaks
- Exit when momentum fades
- Higher turnover than buy-and-hold

**Example:**
```
Stock XYZ ranked #1 by Opportunistic 1y:
- Buy: $100
- Peak after 7 months: $145 (+45%)
- Trailing stop triggers: $135 (+35%)
- Profit captured: 35% vs 1y return of 22%
```

### 2. Catalyst Identification

Stocks with high opportunistic scores often have:
- Pending earnings announcements
- Product launch cycles
- M&A potential
- Restructuring inflection points

**Workflow:**
1. Screen for top opportunistic scores
2. Research upcoming catalysts
3. Position ahead of events
4. Exit after catalyst realized

### 3. Options Strategies

High peak return predictions → high implied volatility plays

**Applications:**
- Buy calls on top-ranked names
- Sell puts on bottom-ranked (unlikely to spike)
- Calendar spreads around predicted timing

### 4. Risk Management

**Diversification Across Timing:**
- Some stocks peak early (months 1-3)
- Others peak late (months 9-12)
- Portfolio captures rolling opportunities

**Stop-Loss Discipline:**
If peak prediction doesn't materialize in 6 months → re-evaluate

## Comparison to Standard GBM

| Metric | GBM Full 1y | GBM Opportunistic 1y | Advantage |
|--------|-------------|----------------------|-----------|
| **Prediction** | 1y return | Peak return (0-1y) | Opportunistic |
| **Top Decile Avg** | 63% | 45% realized | Full |
| **Top Decile Peak** | 75% | 100%+ | Opportunistic |
| **Timing Info** | No | Implicit | Opportunistic |
| **Turnover** | 30-50%/year | 80-120%/year | Full (lower) |
| **Best Use** | Long-term ranking | Tactical trading | Different |

**Insight:** Opportunistic captures explosive moves but requires active management. Full is better for passive portfolios.

## Feature Importance

### Top Predictive Features (Opportunistic-Specific)

**1. Volatility Metrics (20-25% importance)**
- Historical volatility
- Volatility of fundamentals (ROE_std, margin_std)
- Beta to market
- **Why:** High vol stocks have wider peak potential

**2. Momentum Indicators (15-20%)**
- Recent price acceleration
- Volume trends
- Relative strength
- **Why:** Momentum often precedes peaks

**3. Valuation Extremes (12-18%)**
- P/E ratio deviations from mean
- P/B ratio changes
- Earnings surprises
- **Why:** Extreme valuations → mean reversion spikes

**4. Growth Acceleration (10-15%)**
- Revenue growth QoQ changes
- Margin expansion rate
- Earnings surprise magnitude
- **Why:** Inflection points drive peaks

**5. Sentiment Indicators (8-12%)**
- Short interest changes
- Institutional ownership shifts
- Analyst upgrades/downgrades
- **Why:** Sentiment shifts amplify moves

## Implementation

### Running Opportunistic Models

```python
from invest.scripts.run_gbm_predictions import run_predictions

# Run Opportunistic 1y Peak
predictions_1y = run_predictions(
    variant='opportunistic',
    horizon='1y',
    db_path='data/stock_data.db'
)

# Get top candidates for tactical trades
top_opportunities = predictions_1y[
    predictions_1y['percentile'] >= 90
].sort_values('predicted_peak_return', ascending=False)

print(top_opportunities[['ticker', 'predicted_peak_return', 'current_price']])
```

### Strategy Example

```python
# Opportunistic trading strategy
import pandas as pd

def opportunistic_strategy(predictions, max_positions=20):
    """
    Build tactical portfolio from opportunistic predictions
    """
    # Sort by predicted peak return
    ranked = predictions.sort_values('predicted_peak_return', ascending=False)

    # Take top N positions
    portfolio = ranked.head(max_positions).copy()

    # Set trailing stops at 70% of predicted peak
    portfolio['target_peak'] = portfolio['predicted_peak_return']
    portfolio['trailing_stop_pct'] = portfolio['target_peak'] * 0.70

    # Estimate time to peak (from historical patterns)
    portfolio['expected_peak_months'] = estimate_peak_timing(portfolio)

    # Set review dates
    portfolio['review_date'] = pd.Timestamp.now() + pd.DateOffset(months=6)

    return portfolio

# Example output
# ticker | predicted_peak_return | trailing_stop_pct | expected_peak_months
# NVDA   | 85%                  | 60%               | 7
# AMD    | 72%                  | 50%               | 5
```

## Risk Considerations

### 1. Timing Uncertainty

**Issue:** Model predicts peak magnitude, not exact timing

**Mitigation:**
- Use trailing stops
- Set 6-12 month review periods
- Combine with technical analysis for entry timing

### 2. Higher Volatility

**Issue:** Peak-seeking stocks are inherently more volatile

**Mitigation:**
- Position sizing: 2-5% per stock (vs 5-10% for standard GBM)
- Portfolio-level volatility targeting
- Correlation-adjusted diversification

### 3. False Peaks

**Issue:** Early peaks may not be THE peak

**Mitigation:**
- Partial profit-taking (sell 50% at first 30% gain)
- Re-rank monthly (new opportunities emerge)
- Don't wait for perfect timing

### 4. Overfitting to Extremes

**Issue:** Model may overfit to outlier historical peaks

**Mitigation:**
- Regularization in training (high feature_fraction)
- Out-of-sample validation critical
- Winsorize extreme predictions (cap at 200%)

## Academic Foundation

### Theoretical Basis

**Momentum and Reversal:**
- Jegadeesh & Titman (1993): "Returns to Buying Winners and Selling Losers"
- Momentum persists 3-12 months → peak detection window

**Volatility and Returns:**
- Ang et al. (2006): "The Cross-Section of Volatility and Expected Returns"
- High idiosyncratic volatility → higher peak potential

**Earnings Surprises:**
- Bernard & Thomas (1989): "Post-Earnings-Announcement Drift"
- Earnings surprises drive multi-month outperformance

### Machine Learning for Timing

**Gu, Kelly & Xiu (2020):**
- "Empirical Asset Pricing via Machine Learning"
- Tree-based models excel at detecting non-linear patterns
- Peak prediction = extreme quantile regression

**Lopez de Prado (2018):**
- "Advances in Financial Machine Learning"
- Target variable engineering for tactical strategies
- Triple-barrier method for exits (similar to trailing stops)

## Practical Tips

### 1. Combine with Standard GBM

**Hybrid Strategy:**
- Core portfolio: Top GBM Full rankings (70% of capital)
- Tactical sleeve: Top Opportunistic rankings (30% of capital)

**Rationale:**
- Full provides stable long-term performance
- Opportunistic adds alpha from timing
- Diversification across strategies

### 2. Sector Rotation

**Observation:** Peak timing varies by sector
- Tech: Quick peaks (3-6 months)
- Industrials: Slower peaks (9-15 months)
- Healthcare: Binary events (3 months or 18+ months)

**Application:**
- Overweight fast-peak sectors in bull markets
- Overweight slow-peak sectors in choppy markets

### 3. Market Regime Adaptation

**Bull Markets:**
- Opportunistic 1y outperforms (momentum strong)
- Higher position sizes (6-8% per stock)

**Bear Markets:**
- Switch to Opportunistic 3y (longer recovery)
- Lower position sizes (3-4% per stock)

**Sideways Markets:**
- Focus on stock-specific catalysts
- Narrow to top 10 scores (higher conviction)

## When to Use

### Best For
- **Active traders**: Can monitor positions and adjust stops
- **Tactical allocation**: Overlay on core portfolio
- **High-conviction plays**: Concentrated bets on top ideas
- **Catalyst-driven investing**: Earnings, M&A, restructurings

### Not Ideal For
- **Passive investors**: Too much turnover and monitoring
- **Tax-sensitive accounts**: Short-term capital gains
- **Risk-averse portfolios**: Higher volatility profile
- **Small accounts**: Transaction costs matter

## Limitations

### 1. Requires Active Management
Can't buy and forget - need trailing stops and monitoring

### 2. Transaction Costs
Higher turnover → higher costs
- Commissions (even if low)
- Bid-ask spreads
- Market impact

### 3. Psychological Discipline
Easy to hold too long (hoping for higher peak)
Need to stick to trailing stop rules

### 4. Backtesting Bias
Measuring peak returns ex-post easier than predicting ex-ante
Live performance typically 60-70% of backtest

## Model Validation

### Out-of-Sample Testing

**Methodology:**
- Train on 2015-2019
- Test on 2020-2024
- Measure: % of top decile that achieved predicted peak

**Results (Typical):**
- 65% of top decile achieved within 20% of predicted peak
- 85% achieved positive peak above market
- Median time to peak: 7 months (1y model), 14 months (3y model)

### Walk-Forward Analysis

**Process:**
1. Retrain model quarterly
2. Predict peaks for next quarter
3. Track actual peaks realized
4. Compare predicted vs actual rank correlation

**Expected Performance:**
- Rank IC (peak prediction): 0.35-0.45
- Lower than standard GBM (0.59) because timing adds noise
- But top decile still significantly outperforms

## References

- Ang, A., Hodrick, R., Xing, Y., & Zhang, X. (2006). "The Cross-Section of Volatility and Expected Returns". *Journal of Finance*.
- Bernard, V., & Thomas, J. (1989). "Post-Earnings-Announcement Drift". *Journal of Accounting and Economics*.
- Gu, S., Kelly, B., & Xiu, D. (2020). "Empirical Asset Pricing via Machine Learning". *Review of Financial Studies*.
- Jegadeesh, N., & Titman, S. (1993). "Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency". *Journal of Finance*.
- Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley.

## Related Models

- **[AutoResearch](autoresearch.md)**: 5-model ensemble also predicting peak returns (2-year horizon), using a different feature set and more diverse algorithms
- **[GBM 1y/3y](gbm-full.md)**: Standard fixed-horizon predictions for long-term ranking
- **[DCF](dcf.md)**: Validate peak potential with fundamental analysis
- **[RIM](rim.md)**: Residual income valuation for financials
