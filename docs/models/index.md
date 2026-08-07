# Valuation Models

The framework employs multiple valuation approaches to provide diverse perspectives on stock value. The dashboard displays 7 active models, each with different strengths, assumptions, and data requirements.

## Active Dashboard Models

These are the models currently shown on the dashboard, listed in display order:

### ML Ensemble

- [AutoResearch](autoresearch.md) - 5-model ensemble predicting peak 2-year returns

### Peak Return Prediction (Opportunistic)

- [GBM Opportunistic 1y](gbm-opportunistic.md) - Peak return prediction within 1 year
- [GBM Opportunistic 3y](gbm-opportunistic.md) - Peak return prediction within 3 years

### Fixed-Horizon Return Prediction

- [GBM 1y](gbm-full.md) - Gradient boosted machine, 1-year return prediction
- [GBM 3y](gbm-full.md) - Gradient boosted machine, 3-year return prediction

### Classic Valuation

- [Discounted Cash Flow (DCF)](dcf.md) - Absolute fair value from projected free cash flows
- [Residual Income Model (RIM)](rim.md) - Book value plus present value of excess returns

## Model Comparison

| Model | Type | Predicts | Coverage | Data Required | Best For |
|-------|------|----------|----------|---------------|----------|
| **AutoResearch** | ML ensemble (5 models) | Peak 2y return | High | Fundamental snapshots + price | Ranking stocks by upside potential |
| **GBM Opp 1y** | Gradient boosting | Peak 1y return | ~52% | 8+ quarters | Tactical trades, timing |
| **GBM Opp 3y** | Gradient boosting | Peak 3y return | ~52% | 8+ quarters | Multi-year opportunities |
| **GBM 1y** | Gradient boosting | 1-year return | ~52% | 8+ quarters | Portfolio construction |
| **GBM 3y** | Gradient boosting | 3-year return | ~52% | 8+ quarters | Long-term ranking |
| **DCF** | Fundamental | Absolute fair value | ~98% | 1+ quarters | Stable cash flow companies |
| **RIM** | Fundamental | Absolute fair value | ~85% | Book value data | Banks, asset-heavy companies |

## How to Use Multiple Models

The dashboard displays all available models for each stock. Consider:

1. **Convergence**: When multiple models agree on upside, confidence is higher
2. **Divergence**: Indicates model assumptions may not fit the business
3. **ML vs Fundamental**: GBM/AutoResearch models rank stocks relatively; DCF/RIM provide absolute fair values
4. **Time Horizons**: Compare 1y vs 3y predictions to assess near-term vs long-term opportunity

## Understanding Predictions

- **Fair Value**: Estimated intrinsic value per share (DCF, RIM) or implied price from predicted return (ML models)
- **Upside %**: Predicted return or margin of safety vs current price
- **Confidence**: Model-specific reliability indicator (rank percentile for ML models)

## Retired Models

The following models were previously available but have been removed from the dashboard:

- **GBM Lite 1y/3y**: Simplified GBM with 59 features and 2-quarter minimum. Removed for being overoptimistic. See [archived docs](gbm-lite.md).
- **Enhanced DCF**: DCF variant accounting for dividend policy. See [archived docs](dcf-enhanced.md).
- **Multi-Stage DCF**: Multiple growth phase DCF. Removed (85% failure rate). See [archived docs](multi-stage-dcf.md).
- **Growth DCF**: Separated growth vs maintenance CapEx. Removed (85% failure rate). See [archived docs](growth-dcf.md).
- **Simple Ratios**: Market multiples valuation. Removed (broken). See [archived docs](simple-ratios.md).

For detailed information on each active model, click the links above.
