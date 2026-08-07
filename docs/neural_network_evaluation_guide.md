# Neural Network Model Evaluation Guide

## Overview

The neural network valuation model has been enhanced with:

1. **Comprehensive confidence metrics** based on data quality, extreme values, sector volatility, market cap, and analyst coverage
2. **Rigorous evaluation framework** with proper train/test/validation splits
3. **Cross-model comparison** to understand when NN differs from DCF, Graham, and ratio models
4. **Sector and decade-based analysis** to identify strengths and weaknesses

## Current Status

**⚠️ Model needs training** - You just cloned the repo, so no trained model exists yet.

## Quick Start

### 1. Train the Model (First Time)

```bash
# Train with 20 years of data (2004-2024)
uv run python models/neural_network/training/comprehensive_neural_training.py

# Monitor progress in another terminal
uv run python scripts/training_monitor.py
```

Training will:
- Sample 5,000+ data points from 80+ stocks across 8 sectors
- Cover multiple market cycles (2008 crash, 2020 COVID, etc.)
- Use early stopping to prevent overfitting
- Save best model to `models/neural_network_1year.pth`

Expected duration: 30-60 minutes

### 2. Evaluate the Model

```bash
# Run comprehensive evaluation
uv run python scripts/neural_network_evaluator.py
```

This will generate:
- **Text report**: `evaluation_results/neural_network_evaluation_report.txt`
- **JSON metrics**: `evaluation_results/evaluation_results.json`

The evaluation uses:
- **Train period**: 2004-2019 (16 years)
- **Validation period**: 2020-2021 (2 years)
- **Test period**: 2022-2024 (3 years) - for final evaluation

### 3. Understanding the Results

#### Overall Performance Metrics

```
Mean Absolute Error (MAE):     0.0850 (8.50%)
Root Mean Squared Error (RMSE): 0.1240
R-squared:                      0.6234
Correlation:                    0.7896
```

- **MAE < 10%**: Excellent prediction accuracy
- **R² > 0.6**: Model explains 60%+ of variance
- **Correlation > 0.75**: Strong predictive relationship

#### Confidence Calibration

The model now provides **intelligent confidence scores** based on:

| Factor | Weight | Description |
|--------|--------|-------------|
| Data completeness | 0-5 pts | Missing optional fields reduce confidence |
| Extreme values | 0-5 pts | P/E > 100, high debt, negative margins |
| Sector volatility | 0-3 pts | Tech, Energy, Consumer Cyclical are harder |
| Market cap | 0-2 pts | Small caps are less predictable |
| Prediction extremity | 0-5 pts | Very bullish/bearish scores less reliable |
| Analyst coverage | 0-2 pts | Low coverage reduces confidence |

**Confidence levels:**
- **High** (0-5 pts): Best data quality, established company, reasonable valuation
- **Medium** (5-10 pts): Some missing data or moderate risk factors
- **Low** (10+ pts): Poor data, extreme values, or highly speculative

#### Model Comparison

```
vs DCF Model:        +15.3% improvement
vs Graham Model:     +8.7% improvement
vs Simple Ratios:    +22.1% improvement
```

Positive values = Neural network performs better

#### Prediction Disagreements

The report shows **top 10 cases where NN differs most from other models**. These are worth investigating:

```
1. TSLA   Technology          2022-03-15  NN: +25%, Actual: +18%
   → NN correctly predicted Tesla's resilience vs DCF's conservative estimate

2. XOM    Energy              2022-06-01  NN: -15%, Actual: -8%
   → NN was too bearish on energy during oil price surge
```

**How to investigate:**
1. Look at the features used (P/E, growth, debt, etc.)
2. Check if sector-specific factors were missed
3. Review what the other models predicted and why

#### Sector-Wise Performance

Identifies which sectors the model predicts best:

```
Financial Services:     MAE=0.0620, Corr=0.85, n=234
Healthcare:             MAE=0.0710, Corr=0.82, n=198
Technology:             MAE=0.0980, Corr=0.74, n=312  ← More volatile
Energy:                 MAE=0.1150, Corr=0.68, n=145  ← Hardest to predict
```

**Interpretation:**
- Stable sectors (Financials, Healthcare) → More predictable
- Volatile sectors (Tech, Energy) → Higher errors but still useful

#### Decade-Based Performance

Shows how model performs across market eras:

```
2000s:  MAE=0.0890, Corr=0.76, n=456
2010s:  MAE=0.0780, Corr=0.81, n=523  ← Best (bull market)
2020s:  MAE=0.0920, Corr=0.73, n=287  ← More volatile (COVID, inflation)
```

## Improving the Model

### If accuracy is poor (<70% correlation):

1. **Add more training data**
   - Extend stock universe in `comprehensive_neural_training.py`
   - Add international stocks
   - Include more historical periods

2. **Feature engineering**
   - Add macroeconomic indicators (interest rates, GDP growth)
   - Include sentiment analysis from news
   - Add technical indicators (RSI, MACD)

3. **Architecture changes**
   - Adjust hidden layers in `neural_network_model.py`
   - Try different dropout rates
   - Experiment with batch normalization

### If confidence calibration is poor (<0.7):

The model's confidence should match actual accuracy. If high-confidence predictions aren't actually more accurate:

1. **Adjust uncertainty weights** in `_estimate_uncertainty()`
2. **Collect more validation data** to tune thresholds
3. **Consider ensemble methods** to improve reliability

### If model disagrees with DCF/Graham often:

This isn't always bad! The NN may capture patterns they miss. But investigate:

1. **Feature importance**: Which features drive the NN prediction?
2. **Edge cases**: Does NN handle extreme valuations poorly?
3. **Sector biases**: Is NN too bullish/bearish on certain sectors?

## Advanced Usage

### Evaluate Specific Time Periods

Edit `EvaluationConfig` in `neural_network_evaluator.py`:

```python
config = EvaluationConfig(
    test_start='2008-01-01',  # Great Recession
    test_end='2009-12-31'
)
```

### Test Different Horizons

```python
config.horizons = ['1month', '3month', '1year', '5year']
```

### Export Detailed Results

```python
# In neural_network_evaluator.py
results_df = pd.DataFrame([vars(r) for r in test_results])
results_df.to_csv('detailed_predictions.csv', index=False)
```

## Key Findings to Look For

1. **Sectors where NN excels** → Use it with higher weight
2. **Sectors where NN struggles** → Rely more on DCF/Graham
3. **Market conditions where NN fails** → Build fallback logic
4. **Confidence vs accuracy relationship** → Trust high-confidence predictions more

## Next Steps

After training and evaluation:

1. **Review the worst predictions** (Top 10 errors)
2. **Analyze model disagreements** (Where NN differs from other models)
3. **Adjust confidence thresholds** based on calibration score
4. **Integrate into production** with appropriate confidence filters

## Questions to Answer

- **Is the model reliable?** → Check calibration score and R²
- **When should I trust it?** → Use confidence levels and sector performance
- **How does it compare?** → Review vs_dcf/graham/ratios improvements
- **What are the failure modes?** → Study large errors and disagreements

---

**Remember**: The goal isn't perfect predictions, but **reliable uncertainty estimates**. A model that knows when it's uncertain is more valuable than one that's always confident but often wrong.
