# Testing Guide

## Overview

The test suite uses pytest markers to automatically skip tests that require resources that may not exist (trained models, historical data).

## Test Markers

### `@pytest.mark.requires_models`
Tests that need trained models (GBM, neural networks). These tests will be **automatically skipped** if models don't exist.

**Models checked:**
- `models/neural_network/training/gbm_model_1y.txt`
- `models/neural_network/training/gbm_model_3y.txt`
- `models/neural_network/training/gbm_lite_model_1y.txt`
- `models/neural_network/training/gbm_opportunistic_model_1y.txt`
- `models/neural_network/training/best_model.pt`

**Skip message:**
```
Trained models not found. Train models first with scripts in models/neural_network/training/
```

### `@pytest.mark.requires_data`
Tests that need full database with historical data (1000+ records in `fundamental_history` table). These tests will be **automatically skipped** if data doesn't exist.

**Skip message:**
```
Historical data not found. Run: uv run python scripts/populate_fundamental_history.py
```

### Other Markers
- `@pytest.mark.slow` - Long-running tests (>5 seconds)
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.unit` - Fast unit tests
- `@pytest.mark.performance` - Performance benchmarks

---

## Running Tests

### Default (All tests)
```bash
uv run pytest
```
Runs all tests. Auto-skips tests requiring missing resources.

### Skip Optional Tests
```bash
# Skip tests requiring models
uv run pytest -m "not requires_models"

# Skip tests requiring data
uv run pytest -m "not requires_data"

# Skip both models and data tests
uv run pytest -m "not requires_models and not requires_data"

# Skip slow tests
uv run pytest -m "not slow"
```

### Run Only Specific Tests
```bash
# Run only model tests (if models exist)
uv run pytest -m "requires_models"

# Run only data tests (if data exists)
uv run pytest -m "requires_data"

# Run only unit tests
uv run pytest -m "unit"

# Run specific file
uv run pytest tests/test_gbm_models.py
```

### Verbose Output
```bash
# Show test names and skip reasons
uv run pytest -v

# Show even more details
uv run pytest -vv

# Show print statements
uv run pytest -s
```

---

## Writing Tests with Markers

### Example: Test requiring models

```python
import pytest

@pytest.mark.requires_models
@pytest.mark.requires_data
def test_gbm_predictions():
    """This test needs trained models and historical data."""
    import lightgbm as lgb

    # This won't run if models don't exist
    model = lgb.Booster(model_file='models/neural_network/training/gbm_model_1y.txt')
    assert model is not None
```

### Example: Test that always runs

```python
def test_database_schema():
    """This test always runs (no markers)."""
    import sqlite3
    from pathlib import Path

    db_path = Path('data/stock_data.db')
    if not db_path.exists():
        pytest.skip("Database not found")

    # Check schema
    conn = sqlite3.connect(str(db_path))
    # ...
```

---

## Auto-Skip Logic

The auto-skip behavior is implemented in `tests/conftest.py`:

1. **Before tests run**, pytest checks if required resources exist
2. **If missing**, tests are marked with `@pytest.mark.skip`
3. **Tests show helpful message** explaining what's missing and how to fix it

**Benefits:**
- ✅ Tests pass in CI/CD even without models
- ✅ New developers can run tests without training models first
- ✅ Clear messages tell you how to enable skipped tests
- ✅ No manual marker management needed

---

## CI/CD Integration

### Run fast tests only (for PR checks)
```bash
uv run pytest -m "not requires_models and not requires_data and not slow"
```

### Run all tests (for nightly builds)
```bash
uv run pytest -m ""
```

### Check coverage
```bash
uv run pytest --cov=src/invest --cov-report=html
open htmlcov/index.html
```

---

## Troubleshooting

### Tests are skipped but I have the models
**Check model paths:**
```bash
ls -la models/neural_network/training/*.txt
ls -la models/neural_network/training/*.pt
```

Models must be in the exact locations checked by `conftest.py`.

### Tests are skipped but I have historical data
**Check record count:**
```bash
sqlite3 data/stock_data.db "SELECT COUNT(*) FROM fundamental_history;"
```

Must have at least 1,000 records.

### Want to see why tests were skipped
```bash
uv run pytest -v -rs
```
The `-rs` flag shows skip reasons.

---

## Examples

### Typical Workflow

```bash
# 1. Run fast tests during development
uv run pytest -m "not slow"

# 2. Before committing, run all tests
uv run pytest

# 3. If models missing, train them
cd models/neural_network/training
uv run python train_gbm_stock_ranker.py

# 4. Run model tests
uv run pytest -m "requires_models"
```

### CI/CD Pipeline

```yaml
# .github/workflows/test.yml
jobs:
  fast-tests:
    - name: Run fast tests
      run: uv run pytest -m "not requires_models and not requires_data"

  full-tests:
    - name: Train models
      run: ...
    - name: Populate data
      run: uv run python scripts/populate_fundamental_history.py
    - name: Run all tests
      run: uv run pytest
```

---

## Summary

**Auto-skip markers make tests flexible:**
- ✅ Pass even without models/data
- ✅ Clear messages on what's missing
- ✅ Easy to run subsets of tests
- ✅ CI/CD friendly

**Add markers to new tests:**
```python
@pytest.mark.requires_models  # Needs trained models
@pytest.mark.requires_data     # Needs historical data
@pytest.mark.slow              # Takes >5 seconds
```
