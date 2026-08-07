# GBM Holdout Evaluation

## Purpose

This folder contains rigorous holdout evaluation scripts to verify that our GBM models' high Information Coefficients (ICs) are genuine and not artifacts of overfitting to cross-validation splits.

### The Problem

Our GBM models showed surprisingly high performance on time-series cross-validation:

- **Full GBM 1y**: Rank IC = 0.505 (Decile Spread = 65%)
- **Full GBM 3y**: Rank IC = 0.638 (Decile Spread = 193%)
- **Lite GBM 1y**: Rank IC = 0.573 (Decile Spread = 75%)
- **Lite GBM 3y**: Rank IC = 0.613 (Decile Spread = 197%)

These ICs are exceptionally high for stock market prediction. To verify these aren't overfitting artifacts, we need true out-of-sample testing on the most recent data.

### The Solution

Train models on data **up to December 31, 2023** and evaluate on **2024-2025 data** as a true holdout test set. This ensures:

1. No information leakage from recent market behavior
2. True test of generalization to unseen future data
3. Fair comparison between CV validation and holdout test performance

## Methodology

### Training Cutoff

- **Train data**: All snapshots with `snapshot_date <= 2023-12-31`
- **Holdout test data**: All snapshots with `snapshot_date > 2023-12-31` (2024-2025)

### Evaluation Metrics

For each model, we report **two separate evaluations**:

1. **CV Validation (2021-2023)**: Performance on the last cross-validation fold (within training period)
2. **Holdout Test (2024-2025)**: Performance on true out-of-sample data

### Key Metrics

- **Rank IC**: Spearman correlation between predicted and actual returns
  - 0.05-0.10: Decent
  - 0.10-0.20: Very good
  - 0.20+: Exceptional (or suspicious)

- **Decile Spread**: Return difference between top 10% and bottom 10% of predicted stocks
  - Larger spreads = better ranking ability
  - Should be positive to be useful

### Interpretation

If holdout IC is:
- **> 0.30**: Model performance is GENUINE and exceptional
- **0.15-0.30**: Model is decent but not as strong as CV suggested
- **< 0.15**: Model likely overfitting to CV splits

## Files

### Training Scripts

- `train_gbm_holdout.py`: Full GBM models (463 features, 8 lags)
- `train_gbm_lite_holdout.py`: Lite GBM models (247 features, 2 lags)

Both scripts:
- Accept `--target-horizon` (`1y` or `3y`)
- Accept `--train-cutoff` (default: `2023-12-31`)
- Report both CV validation and holdout test metrics
- Save models with `_holdout` suffix
- Save results to JSON files

### Output Files

- `gbm_model_1y_holdout.txt`: Full GBM 1-year holdout model
- `gbm_model_3y_holdout.txt`: Full GBM 3-year holdout model
- `gbm_lite_model_1y_holdout.txt`: Lite GBM 1-year holdout model
- `gbm_lite_model_3y_holdout.txt`: Lite GBM 3-year holdout model
- `holdout_results_1y.json`: Full GBM 1-year results
- `holdout_results_3y.json`: Full GBM 3-year results
- `holdout_results_lite_1y.json`: Lite GBM 1-year results
- `holdout_results_lite_3y.json`: Lite GBM 3-year results

## Usage

### Train All 4 Holdout Models (Recommended)

```bash
cd neural_network/training/holdout_evaluation

# Full GBM models
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib:$DYLD_LIBRARY_PATH uv run python train_gbm_holdout.py --target-horizon 1y
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib:$DYLD_LIBRARY_PATH uv run python train_gbm_holdout.py --target-horizon 3y

# Lite GBM models
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib:$DYLD_LIBRARY_PATH uv run python train_gbm_lite_holdout.py --target-horizon 1y
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib:$DYLD_LIBRARY_PATH uv run python train_gbm_lite_holdout.py --target-horizon 3y
```

### Sequential Training (to avoid database contention)

```bash
cd neural_network/training/holdout_evaluation

(
echo "=== Holdout Evaluation Training ===" && \
echo "Model 1/4: Full GBM 1-year..." && \
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib:$DYLD_LIBRARY_PATH uv run python train_gbm_holdout.py --target-horizon 1y && \
echo "✓ Full GBM 1y complete" && \
echo "Model 2/4: Full GBM 3-year..." && \
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib:$DYLD_LIBRARY_PATH uv run python train_gbm_holdout.py --target-horizon 3y && \
echo "✓ Full GBM 3y complete" && \
echo "Model 3/4: Lite GBM 1-year..." && \
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib:$DYLD_LIBRARY_PATH uv run python train_gbm_lite_holdout.py --target-horizon 1y && \
echo "✓ Lite GBM 1y complete" && \
echo "Model 4/4: Lite GBM 3-year..." && \
DYLD_LIBRARY_PATH=/opt/homebrew/opt/libomp/lib:$DYLD_LIBRARY_PATH uv run python train_gbm_lite_holdout.py --target-horizon 3y && \
echo "✓ All 4 holdout models trained successfully!"
) > holdout_training.log 2>&1 &
```

Monitor: `tail -f neural_network/training/holdout_evaluation/holdout_training.log`

### Custom Cutoff Date

```bash
# Train with different cutoff (e.g., 2024-06-30)
uv run python train_gbm_holdout.py --target-horizon 1y --train-cutoff 2024-06-30
```

## Results Interpretation

### Example Output

```
==========================================================
HOLDOUT EVALUATION COMPLETE - 1y horizon
==========================================================
CV Validation IC (2021-2023): 0.5052
Holdout Test IC (2024-2025): 0.4823
CV Validation Spread: 0.6535
Holdout Test Spread: 0.5912
==========================================================
✓ Holdout IC > 0.3 - Model performance is GENUINE!
```

### What This Means

- **CV IC = 0.505**: Model performed well during training period
- **Holdout IC = 0.482**: Model generalized well to 2024-2025 (only 4.5% drop)
- **Conclusion**: High IC is genuine, not overfitting

### Scenarios

#### Scenario 1: Performance Maintained (Good Sign)
```
CV IC: 0.50
Holdout IC: 0.48
→ Model is robust and genuinely predictive
```

#### Scenario 2: Moderate Drop (Warning Sign)
```
CV IC: 0.50
Holdout IC: 0.22
→ Some overfitting, but model still useful
```

#### Scenario 3: Severe Drop (Bad Sign)
```
CV IC: 0.50
Holdout IC: 0.08
→ Model severely overfit to CV splits, not reliable
```

## Next Steps

### If Holdout IC is Good (> 0.30)

1. **Retrain on full dataset**: Train final production model using ALL data (2000-2025)
2. **Deploy with confidence**: Use these models for actual stock selection
3. **Monitor live performance**: Track real-time IC to ensure it holds

### If Holdout IC Drops Significantly (< 0.15)

1. **Investigate features**: Check which features caused overfitting
2. **Simplify model**: Reduce feature count or tree depth
3. **Re-evaluate methodology**: Consider different validation strategies

## Technical Details

### Data Preprocessing

Same as main training scripts:
1. Load fundamentals + price features
2. Engineer features (lags, changes, rolling stats)
3. Winsorize (1st-99th percentile per date)
4. Standardize (z-score per date)
5. Cross-sectional normalization (regime-agnostic)

### Model Configuration

**Full GBM** (463 features):
- Lag periods: [1, 2, 4, 8] quarters
- Rolling windows: [4, 8, 12] quarters
- Min data requirement: ~2 years history

**Lite GBM** (247 features):
- Lag periods: [1, 2] quarters
- Rolling windows: [4] quarters
- Min data requirement: 4-6 quarters (for newer stocks)

Both models use:
- LightGBM with regression objective
- 127 leaf nodes, depth 7
- 0.05 learning rate
- Early stopping (50 rounds)
- Fixed random seeds (42) for reproducibility

### Cross-Validation

Even within the training period, we use:
- 5-fold purged time-series CV
- 365-day purge for 1y models (1095 for 3y)
- 21-day embargo period
- Grouped by ticker (no leakage across folds)

## **ACTUAL HOLDOUT RESULTS** (2022 Cutoff)

| Model | CV IC (2006-2022) | Holdout IC (2023) | Drop % | Holdout Spread | Status |
|-------|-------------------|-------------------|--------|----------------|---------|
| **Full 1y** | 0.636 | **0.213** | 67% | 28.9% | ⚠️ Decent |
| **Full 3y** | 0.638 | **N/A*** | — | — | ⚠️ No Data |
| **Lite 1y** | 0.580 | **0.174** | 70% | 23.9% | ⚠️ Decent |
| **Lite 3y** | 0.613 | **N/A*** | — | — | ⚠️ No Data |

**Date**: October 15, 2025
**Training**: 2006-2022 data
**Testing**: 2023 data

### ⚠️ **CRITICAL FINDINGS**

#### 1. Models Have Real (But More Modest) Predictive Power

**Good News**:
- Both 1y models show genuine predictive ability on unseen 2023 data
- Holdout ICs of 0.17-0.21 are **still decent** for stock market prediction
- Models are NOT purely overfitting - they learned real patterns

**Reality Check**:
- CV ICs (0.58-0.64) were **significantly inflated** by data leakage or overfitting
- True out-of-sample performance is **~30%** of CV performance
- The gap between CV and holdout is concerning but not catastrophic

#### 2. 3-Year Models Cannot Be Evaluated

***Forward returns require FUTURE price data to calculate.**

- To test a 2023 snapshot with 3y horizon, we need 2026 prices (don't exist yet)
- **Lesson**: Long-horizon models need correspondingly long wait times for validation
- **Solution**: Use shorter cutoffs (2020→2023 test) or wait for time to pass

### Interpretation

**Full GBM 1y** (Rank IC: 0.213, Spread: 28.9%):
- ⚠️ Shows some overfitting (dropped from 0.64 to 0.21)
- ✅ But IC > 0.15 indicates real predictive power
- ✅ Can rank stocks better than random (29% spread between top/bottom deciles)
- **Recommendation**: Use with caution; expect modest not exceptional performance

**Lite GBM 1y** (Rank IC: 0.174, Spread: 23.9%):
- ⚠️ Similar overfitting pattern (dropped from 0.58 to 0.17)
- ✅ Still has predictive value (IC > 0.15)
- ✅ Simpler model (247 vs 463 features) trades some accuracy for generalization
- **Recommendation**: Good for stocks with limited history; similar caveats apply

## References

- **Original training scripts**: `../train_gbm_stock_ranker.py`, `../train_gbm_lite_stock_ranker.py`
- **Feature configs**: `../gbm_feature_config.py`, `../gbm_lite_feature_config.py`
- **Database**: `../../../data/stock_data.db`

## Notes

- Training time: ~2-3 minutes per model on M2 MacBook Pro
- Database size: 1.4GB (38M price history records)
- Run sequentially to avoid SQLite contention issues
- Models saved in parent directory with `_holdout` suffix
- Results also saved as JSON for programmatic access
