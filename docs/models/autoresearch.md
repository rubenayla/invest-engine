# AutoResearch

5-model ensemble predicting **peak 2-year returns** using fundamental, momentum, and macro features.

## Overview

AutoResearch is the highest-priority model on the dashboard. It uses a diverse ensemble of five machine learning algorithms to predict the maximum return a stock could achieve within a 2-year forward window. The ensemble blends gradient boosting (LightGBM DART, CatBoost), instance-based learning (two KNN variants), and bagged decision trees to produce robust rank-based predictions.

## Key Characteristics

| Property | Value |
|----------|-------|
| **Target** | Peak return within 2 years (504 trading days) |
| **Ensemble** | 5 models, rank-blended |
| **Metric** | Spearman rank correlation |
| **Features** | ~55 base + ~25 engineered |
| **Training data** | All fundamental_history snapshots with price data |

## How It Works

### 1. Target Variable

Unlike fixed-horizon models, AutoResearch predicts the **maximum** price gain observed at any point in the next 2 years:

```
peak_return = max(close[t : t + 504 trading days]) / close[t] - 1
```

This captures stocks that spike significantly even if they later give back gains.

### 2. Feature Set

**Fundamental features (45 base)**:

- Valuation: PE, PB, PS, PEG, EV/Revenue, EV/EBITDA
- Profitability: profit margins, operating margins, gross margins, EBITDA margins, ROA, ROE
- Growth: revenue growth, earnings growth, quarterly earnings growth
- Balance sheet: debt-to-equity, current ratio, quick ratio, total cash, total debt
- Cash flow: operating cash flow, free cash flow, trailing/forward EPS, book value
- Dividends: yield, payout ratio, dividend rate
- Market context: VIX, 10Y Treasury, dollar index, oil price, gold price
- Stock-level: market cap, shares outstanding, beta, volatility

**Price/momentum features (9)**:

- Returns: 1-month, 3-month, 6-month, 1-year
- 60-day annualized volatility
- Distance from 52-week high and low
- Price relative to 50-day and 200-day moving averages

**Engineered features (~25)**:

- Log transforms of skewed variables (market cap, volume, cash, debt, cash flows)
- Derived yields: FCF yield, OCF yield, earnings yield
- Net debt and net-debt-to-market-cap ratio
- Momentum composite (average of return windows) and momentum reversal (1m vs 1y)
- Rank-based valuation composite (percentile ranks of PE, PB, PS, EV/EBITDA)
- Rank-based quality composite (percentile ranks of ROE, ROA, profit margins, operating margins)
- Growth composite (average of revenue and earnings growth)
- Volatility-adjusted momentum (6-month Sharpe)
- Distance-from-high / volatility ratio
- VIX x drawdown interaction (fear + value = opportunity signal)

### 3. The 5-Model Ensemble

Each model trains on log-transformed, winsorized (5th-95th percentile) peak returns:

| # | Algorithm | Key Hyperparameters |
|---|-----------|-------------------|
| 1 | **LightGBM DART** | 500 rounds, 127 leaves, depth 10, lr 0.05, drop rate 0.1 |
| 2 | **CatBoost** | 1500 iterations, depth 8, lr 0.02, MAE loss |
| 3 | **KNN (k=15)** | Distance-weighted, StandardScaler preprocessing |
| 4 | **KNN (k=100)** | Uniform weights, broad neighborhood averaging |
| 5 | **Bagged Decision Trees** | 500 estimators, max depth 12, 80% sample / 70% feature bagging |

### 4. Rank-Based Blending

Final predictions use a two-step blend:

1. **Rank blend**: Each model's predictions are converted to ranks, then averaged. This makes the ensemble robust to scale differences between models.
2. **Return estimate**: The arithmetic mean of log-space predictions from all 5 models is converted back via `expm1()` to produce a predicted peak return in percentage terms.

### 5. Confidence Score

Confidence is derived from the rank-blend percentile, scaled to the 0.5-1.0 range. Higher-ranked stocks get higher confidence.

## Prediction Output

For each stock, AutoResearch produces:

- **Fair value**: `current_price * (1 + predicted_peak_return)`
- **Upside %**: The predicted peak return as a percentage
- **Confidence**: 0.5-1.0 based on rank percentile
- **Details**: Predicted peak return, ranking percentile, ensemble composition

## Why 5 Models?

The ensemble is designed for maximum prediction diversity:

- **LightGBM DART** and **CatBoost**: Two different gradient boosting implementations with different regularization strategies (DART dropout vs L2 leaf regularization). Captures non-linear feature interactions.
- **KNN k=15**: Finds the 15 most similar historical snapshots by feature profile. Captures local patterns that tree models may miss.
- **KNN k=100**: Broader neighborhood provides a smoother, more stable baseline prediction.
- **Bagged Decision Trees**: Random subsampling of both rows and features provides orthogonal diversity to the boosted models.

Rank-blending ensures that even if one model produces poorly calibrated raw predictions, its relative ordering still contributes signal.

## When AutoResearch Works Best

### Ideal Candidates

- Stocks with sufficient fundamental history in the database
- Companies where price momentum and fundamentals jointly predict future peaks
- Value + momentum situations (high drawdown + improving fundamentals)

### Less Reliable

- Very recently listed stocks with minimal snapshot history
- Companies undergoing fundamental regime changes not captured in historical patterns
- Pure macro-driven moves (model has macro features but limited macro history)

## Relationship to Other Models

- **GBM Opportunistic**: Also predicts peak returns, but uses the GBM Full feature set (464 features, 8+ quarter history). AutoResearch uses a simpler feature set but a more diverse ensemble.
- **GBM 1y/3y**: Predict fixed-horizon returns rather than peaks. Better for passive portfolio construction.
- **DCF/RIM**: Fundamental valuation models providing absolute fair value estimates. AutoResearch is ML-based and relative/ranking-oriented.

## Implementation

```python
# Run predictions
uv run python scripts/run_autoresearch_predictions.py

# Results saved to valuation_results table with model_name='autoresearch'
```

### Source Files

- Training/evaluation framework: `models/autoresearch/evaluate.py` (fixed, read-only)
- Model implementation: `models/autoresearch/train.py`
- Production prediction script: `scripts/run_autoresearch_predictions.py`

## Known Limitations

1. **Peak return bias**: Predicting peaks is inherently easier in backtesting than live trading, since you need to recognize and exit near the peak in real time.
2. **2-year horizon**: Long prediction window means the model may rank a stock highly even if the peak is 18+ months away.
3. **No timing signal**: The model predicts magnitude of peak return but not when it occurs.
4. **Target winsorization**: Capping at 5th/95th percentile reduces sensitivity to extreme outliers but may underpredict truly explosive moves.
