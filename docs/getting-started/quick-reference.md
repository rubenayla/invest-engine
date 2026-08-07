# Quick Reference

Command reference for common operations.

## Update All Predictions

### Simple (Shell Script)
```bash
./scripts/update_all.sh
```

### Detailed (Python Script with Timing)
```bash
# Run everything
uv run python scripts/run_all_predictions.py

# Run only specific models
uv run python scripts/run_all_predictions.py --models gbm
uv run python scripts/run_all_predictions.py --models nn
uv run python scripts/run_all_predictions.py --models classic
uv run python scripts/run_all_predictions.py --models gbm,nn

# Skip dashboard
uv run python scripts/run_all_predictions.py --skip-dashboard
```

---

## Run Individual Models

### GBM Models
```bash
# Standard GBM
uv run python scripts/run_gbm_predictions.py --variant standard --horizon 1y
uv run python scripts/run_gbm_predictions.py --variant standard --horizon 3y

# Lite (for stocks with limited history)
uv run python scripts/run_gbm_predictions.py --variant lite --horizon 1y
uv run python scripts/run_gbm_predictions.py --variant lite --horizon 3y

# Opportunistic (max price in window)
uv run python scripts/run_gbm_predictions.py --variant opportunistic --horizon 1y
uv run python scripts/run_gbm_predictions.py --variant opportunistic --horizon 3y
```

### Neural Network Models
```bash
# Multi-horizon NN predictions (writes into valuation_results)
uv run python scripts/run_multi_horizon_predictions.py
```

### Classic Valuations (DCF, RIM, etc.)
```bash
uv run python scripts/run_classic_valuations.py
```

### Generate Dashboard
```bash
uv run python scripts/dashboard.py
```

---

## View Results

**Dashboard**: Open `dashboard/valuation_dashboard.html` in browser

**Database**:
```bash
sqlite3 data/stock_data.db "SELECT ticker, model_name, upside_pct FROM valuation_results ORDER BY upside_pct DESC LIMIT 10;"
```

---

## Common Workflows

### Daily Update
```bash
./scripts/update_all.sh
# Then open dashboard/valuation_dashboard.html
```

### Test Single Model
```bash
uv run python scripts/run_gbm_predictions.py --variant standard --horizon 1y
```

### Refresh Only GBM Models
```bash
uv run python scripts/run_all_predictions.py --models gbm
```

---

## Database Info

**Location**: `data/stock_data.db`

**Main Tables**:

| Table | Description |
|-------|-------------|
| `current_stock_data` | Current snapshot (598 stocks) |
| `valuation_results` | All model predictions with timestamps |
| `snapshots` | Historical fundamentals (358 stocks) |
| `price_history` | Historical prices |

**Model Names**:

- `gbm_1y`, `gbm_3y`
- `gbm_lite_1y`, `gbm_lite_3y`
- `gbm_opportunistic_1y`, `gbm_opportunistic_3y`
- `nn_1y`, `nn_3y`
- `dcf`, `dcf_enhanced`, `growth_dcf`, `multi_stage_dcf`
- `rim`, `simple_ratios`

---

## Testing

### Run Tests

```bash
# Run all tests
uv run pytest

# Run only fast tests (skip model tests)
uv run pytest -m "not requires_models"

# Run only model tests (requires trained models)
uv run pytest -m "requires_models"

# Run specific test file
uv run pytest tests/test_gbm_models.py

# Verbose output
uv run pytest -v
```

### Test Markers

Tests are marked with these categories:

| Marker | Description |
|--------|-------------|
| `requires_models` | Needs trained models (GBM, NN). Auto-skipped if models missing. |
| `requires_data` | Needs full database with historical data. Auto-skipped if missing. |
| `slow` | Long-running tests (>5 seconds) |
| `integration` | Integration tests |
| `unit` | Fast unit tests |

**Auto-skip behavior**: Tests marked with `requires_models` or `requires_data` will automatically be skipped if the resources don't exist. You'll see a helpful message:

```
SKIPPED [1] tests/test_gbm_models.py:15: Trained models not found. Train models first with scripts in models/neural_network/training/
```

---

## Help

```bash
# Script help
uv run python scripts/run_gbm_predictions.py --help
uv run python scripts/run_all_predictions.py --help

# List all test markers
uv run pytest --markers
```
