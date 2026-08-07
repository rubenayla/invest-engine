# Neural Network Models — Status

## Multi-Horizon NN (`multi_horizon_model.pt`)

**Status: NOT RELIABLE — disabled from dashboard and consensus (2026-02-21)**

### What it does
Predicts forward excess returns vs SPY at 5 horizons (1m, 3m, 6m, 1y, 2y) using 47 fundamental features from `fundamental_history`.

### Current test metrics (chronological split)
| Horizon | MAE | RMSE | Correlation |
|---------|-----|------|-------------|
| 1m | 5.54% | 7.47% | 0.014 |
| 3m | 9.88% | 13.07% | 0.044 |
| 6m | 14.35% | 19.39% | -0.026 |
| 1y | 22.50% | 30.61% | -0.009 |
| 2y | 43.13% | 65.48% | 0.044 |

Correlations are essentially zero — the model has no predictive power.

### Training data
- 21,599 monthly samples (2006-01 to 2024-01), excess returns vs SPY
- Only ~100 tickers have fundamentals before 2024 (609/712 start in 2024)
- Carry-forward fundamentals with monthly re-sampling

### What was fixed (2026-02-21)
- **Scaler bug**: RobustScaler is now saved in the checkpoint and loaded at inference
- **Excess returns**: targets are now stock return minus SPY return (removes market direction noise)
- **More data**: monthly sampling gives 3.4x more samples than one-per-snapshot

### Why it still doesn't work
1. **Feature poverty**: 47 fundamental ratios alone lack stock-specific signal. Need time-series momentum, technical indicators, analyst estimates, sector-relative metrics.
2. **Limited history**: most tickers only have 1 fundamental snapshot (from 2024), so monthly carry-forward just repeats the same values across months.
3. **Architecture**: simple feedforward NN may not capture the non-linear interactions needed.

### To re-enable
When test correlation consistently exceeds 0.05 across horizons:
1. Uncomment NN in `src/invest/dashboard_components/html_generator.py`
2. Uncomment NN in `scripts/update_all.sh` and `scripts/update_all.py`
3. Uncomment `multi_horizon_nn` weight in `src/invest/config/constants.py`

### Legacy single-horizon models
The `trained_nn_*.pt` files are older single-horizon models — also not reliable.
