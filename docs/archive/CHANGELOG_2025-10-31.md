# Code Improvements - 2025-10-31

## Summary

Reduced code duplication and improved repository organization.

---

## 1. Created Unified GBM Prediction Script

**Before**: 6 separate scripts (2,520 lines total)
- `run_gbm_1y_predictions.py` (405 lines)
- `run_gbm_3y_predictions.py` (405 lines)
- `run_gbm_lite_1y_predictions.py` (452 lines)
- `run_gbm_lite_3y_predictions.py` (452 lines)
- `run_gbm_opportunistic_1y_predictions.py` (403 lines)
- `run_gbm_opportunistic_3y_predictions.py` (403 lines)

**After**: 1 unified script (550 lines)
- `run_gbm_predictions.py` with `--variant` and `--horizon` args

**Lines saved**: ~1,970 lines

### Usage

Old way (6 commands):
```bash
uv run python scripts/run_gbm_1y_predictions.py
uv run python scripts/run_gbm_3y_predictions.py
uv run python scripts/run_gbm_lite_1y_predictions.py
uv run python scripts/run_gbm_lite_3y_predictions.py
uv run python scripts/run_gbm_opportunistic_1y_predictions.py
uv run python scripts/run_gbm_opportunistic_3y_predictions.py
```

New way (6 commands, but same code):
```bash
uv run python scripts/run_gbm_predictions.py --variant standard --horizon 1y
uv run python scripts/run_gbm_predictions.py --variant standard --horizon 3y
uv run python scripts/run_gbm_predictions.py --variant lite --horizon 1y
uv run python scripts/run_gbm_predictions.py --variant lite --horizon 3y
uv run python scripts/run_gbm_predictions.py --variant opportunistic --horizon 1y
uv run python scripts/run_gbm_predictions.py --variant opportunistic --horizon 3y
```

### How It Works

The unified script dynamically imports the correct configuration based on variant:

- **Standard**: Uses `gbm_feature_config.py` + `train_gbm_stock_ranker.py`
- **Lite**: Uses `gbm_lite_feature_config.py` + `train_gbm_lite_stock_ranker.py`
- **Opportunistic**: Uses `gbm_feature_config.py` + `train_gbm_opportunistic.py`

Then loads the correct model file:
- `gbm_model_1y.txt` / `gbm_model_3y.txt`
- `gbm_lite_model_1y.txt` / `gbm_lite_model_3y.txt`
- `gbm_opportunistic_model_1y.txt` / `gbm_opportunistic_model_3y.txt`

And saves to the correct database model name:
- `gbm_1y` / `gbm_3y`
- `gbm_lite_1y` / `gbm_lite_3y`
- `gbm_opportunistic_1y` / `gbm_opportunistic_3y`

---

## 2. Created Master Update Script

**New**: `scripts/update_all.sh`

Runs all models and generates dashboard with one command:

```bash
./scripts/update_all.sh
```

This executes:
1. All 6 GBM variants (standard, lite, opportunistic × 1y, 3y)
2. Neural network models (1y, 3y)
3. Classic valuations (DCF, RIM, etc.)
4. Dashboard generation

---

## 3. Cleaned Up Repository

### Archived Old Scripts
- Moved 6 duplicate GBM scripts to `scripts/archive/`
- Can be deleted later once unified script is proven stable

### Fixed Git Tracking
- Added `tmp.md` to `.gitignore` (no longer tracked)
- Added `todo.md` to `.gitignore` (personal notes, not tracked)

---

## 4. Benefits

### Maintainability
- **One place** to fix bugs instead of 6
- **One place** to add features instead of 6
- Changes to feature engineering apply to all variants automatically

### Consistency
- All variants use identical logic
- Reduces risk of divergence between scripts
- Easier to ensure all models follow best practices

### Developer Experience
- Less code to review
- Easier to understand system architecture
- Clearer separation between model variants

---

## Files Changed

### Created
- ✅ `scripts/run_gbm_predictions.py` (550 lines)
- ✅ `scripts/update_all.sh` (25 lines)
- ✅ `scripts/archive/` directory

### Modified
- ✅ `.gitignore` (added tmp.md, todo.md)

### Moved
- ✅ `scripts/run_gbm_1y_predictions.py` → `scripts/archive/`
- ✅ `scripts/run_gbm_3y_predictions.py` → `scripts/archive/`
- ✅ `scripts/run_gbm_lite_1y_predictions.py` → `scripts/archive/`
- ✅ `scripts/run_gbm_lite_3y_predictions.py` → `scripts/archive/`
- ✅ `scripts/run_gbm_opportunistic_1y_predictions.py` → `scripts/archive/`
- ✅ `scripts/run_gbm_opportunistic_3y_predictions.py` → `scripts/archive/`

---

## 5. Added Database Indexes

Added performance indexes to `valuation_results` table:

```sql
CREATE INDEX idx_valuation_ticker_model ON valuation_results(ticker, model_name);
CREATE INDEX idx_valuation_upside ON valuation_results(upside_pct DESC);
CREATE INDEX idx_valuation_timestamp ON valuation_results(timestamp DESC);
```

**Impact**: Faster dashboard generation and queries.

---

## 6. Created Python Runner Script

**New**: `scripts/run_all_predictions.py`

Python version of update script with:
- ✅ Colored output (success/error/info)
- ✅ Timing per model
- ✅ Summary statistics
- ✅ Exit codes for CI/CD
- ✅ Selective model running

### Usage

```bash
# Run everything
uv run python scripts/run_all_predictions.py

# Run only specific models
uv run python scripts/run_all_predictions.py --models gbm,nn
uv run python scripts/run_all_predictions.py --models classic

# Skip dashboard generation
uv run python scripts/run_all_predictions.py --skip-dashboard
```

---

## Quick Reference

### Run All Predictions

**Option 1: Shell script** (simple)
```bash
./scripts/update_all.sh
```

**Option 2: Python script** (detailed output, timing)
```bash
uv run python scripts/run_all_predictions.py
```

### Run Single Model

**GBM variants:**
```bash
uv run python scripts/run_gbm_predictions.py --variant standard --horizon 1y
uv run python scripts/run_gbm_predictions.py --variant lite --horizon 3y
uv run python scripts/run_gbm_predictions.py --variant opportunistic --horizon 1y
```

**Neural networks:**
```bash
uv run python scripts/run_nn_predictions.py
uv run python scripts/run_nn_3y_predictions.py
```

**Classic valuations:**
```bash
uv run python scripts/run_classic_valuations.py
```

---

## Next Steps (Optional)

1. **Test the unified script** with one variant:
   ```bash
   uv run python scripts/run_gbm_predictions.py --variant standard --horizon 1y
   ```

2. **Run all models** with the new script:
   ```bash
   uv run python scripts/run_all_predictions.py
   ```

3. **Delete archived scripts** once confident (or keep as backup):
   ```bash
   # After testing, optionally:
   rm -rf scripts/archive/
   ```

4. **Similar unification for neural network scripts**?
   - `run_nn_predictions.py` + `run_nn_3y_predictions.py` could also be unified
   - Would save another ~400 lines

---

## Testing Checklist

- [ ] Test standard 1y: `uv run python scripts/run_gbm_predictions.py --variant standard --horizon 1y`
- [ ] Test lite 3y: `uv run python scripts/run_gbm_predictions.py --variant lite --horizon 3y`
- [ ] Test opportunistic 1y: `uv run python scripts/run_gbm_predictions.py --variant opportunistic --horizon 1y`
- [ ] Verify database has predictions for all 6 variants
- [ ] Test master update script: `./scripts/update_all.sh`
- [ ] Verify dashboard generates correctly

---

**Lines of code saved**: ~1,970
**Scripts reduced**: 6 → 1
**Time to add new feature**: 6× faster (change once vs 6 times)
