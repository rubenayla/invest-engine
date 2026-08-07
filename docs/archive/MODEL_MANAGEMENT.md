# Neural Network Model Management

Quick reference for working with the production LSTM/Transformer model.

## Current Production Model

**File:** `models/neural_network/training/best_model.pt` (11MB)

**Performance:**
- MAE: 23.05%
- Correlation: 0.4421
- Hit Rate: 78.64%
- Training: 2,567 samples (2006-2020)
- Test: 199 samples (2022)

**Model format:** PyTorch `.pt` file containing:
- Model state dict (LSTM/Transformer weights)
- Architecture: 11 temporal features, 22 static features
- Target: 1-year forward returns
- Portable across Mac, Linux, Windows

---

## Using Models

### Load and Use

```python
from pathlib import Path
import torch
from invest.valuation.lstm_transformer_model import LSTMTransformerNetwork

# Load model
model_path = Path('models/neural_network/training/best_model.pt')
checkpoint = torch.load(model_path, map_location='cpu')

model = LSTMTransformerNetwork(
    temporal_features=11,
    static_features=22
).to('cpu')

model.load_state_dict(checkpoint)
model.eval()

# Make predictions (see SINGLE_HORIZON_NN.md for full usage)
```

### Model Registry Integration

```python
from src.invest.valuation.model_registry import ModelRegistry

registry = ModelRegistry()

# Register your model
registry.register_model('neural_network', {
    'model_path': 'trained_nn_2year_comprehensive.pt',
    'time_horizon': '2year'
})

# Use through registry
model = registry.get_model('neural_network')
```

---

## Training Workflow

All training is done locally on Mac - no need for GPU or cloud instances.

### 1. Validate Data Quality

```bash
cd models/neural_network/training
uv run python validate_data_quality.py
```

Expected output:
```
✅ All critical checks passed!
   No issues found.
```

### 2. (Optional) Refresh Data

```bash
cd models/neural_network/training
uv run python create_multi_horizon_cache.py
```

This fetches fresh fundamental data from yfinance and populates:
- `data/stock_data.db` (1.4GB SQLite)
- 3,534+ snapshots from 100+ stocks (2006-present)
- Forward returns for all horizons

**Duration:** ~30 minutes for full refresh

### 3. Train Model

```bash
cd models/neural_network/training
uv run python train_single_horizon.py --epochs 100 --batch-size 32 --learning-rate 0.001
```

Output:
- `best_model.pt` - Saved automatically when validation loss improves
- Early stopping typically at epoch 10-15

**Training time:** ~10 seconds on M1 Mac

### 4. Evaluate

```bash
cd models/neural_network/training
uv run python evaluate_model.py
```

Generates:
- `evaluation_results/evaluation_report.txt` - Performance summary
- `evaluation_results/detailed_results.csv` - Per-stock predictions

---

## Model Comparison

### Compare Phases

**Phase 1 vs Phase 2 Performance:**

| Metric | Phase 1 (Incomplete Data) | Phase 2 (Production) | Improvement |
|--------|--------------------------|----------------------|-------------|
| MAE | 24.90% | 23.05% | 1.85% better |
| Correlation | 0.0056 | 0.4421 | **78x better** |
| Hit Rate | 59.07% | 78.64% | +19.57% |
| Samples | ~700 | 2,567 training | 3.7x more data |

**What changed:**
- Fixed 0% → 92-100% feature coverage
- Proper chronological split (no data leakage)
- Fresh data through 2023

See `stuff.md` for the full development journey.

---

## Improvements Made

### 1. Macroeconomic Features ✅

Added 7 macro features to capture market context:
- Fed funds rate
- 10-year Treasury yield
- VIX (volatility index)
- S&P 500 P/E ratio
- GDP growth
- Inflation rate
- Unemployment rate

**Impact**: Model now considers market conditions, not just company fundamentals.

### 2. Recent Data Focus ✅

Changed training period from 2004-2024 → 2015-2024:
- Better data quality (fewer missing values)
- More relevant to current market
- All major tech companies covered

**Expected improvement**: +20-30% better correlation

### 3. Enhanced Confidence System ✅

Multi-factor confidence scoring:
- Data completeness (0-5 points)
- Extreme values (0-5 points)
- Sector volatility (0-3 points)
- Market cap size (0-2 points)
- Prediction extremity (0-5 points)
- Analyst coverage (0-2 points)

**Result**: More reliable uncertainty estimates

---

## Next Training Run

### Recommended Settings

```python
# In models/neural_network/training/comprehensive_neural_training.py

TrainingConfig(
    start_year=2015,          # ← Changed from 2004
    end_year=2024,
    target_samples=10000,     # ← Increase from 5000
    max_total_epochs=300,     # ← More training
    patience=20               # ← More patience
)
```

### Expected Results

With these improvements:
- **Current**: Correlation 0.158 (R² ≈ 0.025)
- **Expected**: Correlation 0.35-0.45 (R² ≈ 0.12-0.20)
- **Best case**: Correlation 0.50+ (R² ≈ 0.25)

Note: Stock prediction is inherently difficult. Even 0.35 correlation is very good!

---

## Training on Different Hardware

### Performance Estimates

| Hardware | 5K samples | 10K samples | Cost |
|----------|-----------|-------------|------|
| M1 Mac (CPU) | 45 min | 90 min | $0 |
| M1 Max (CPU) | 30 min | 60 min | $0 |
| Intel i7 (CPU) | 60 min | 120 min | $0 |
| RTX 3080 (GPU) | 5 min | 10 min | ~$1 cloud |
| A100 (GPU) | 2 min | 4 min | ~$2 cloud |

### Cloud Options

**AWS EC2 p3.2xlarge (V100):**
```bash
# Launch
aws ec2 run-instances --instance-type p3.2xlarge ...

# Train (10K samples)
# Time: ~8 minutes
# Cost: ~$0.40 (at $3/hr)
```

**Google Colab (Free):**
- Free Tesla T4 GPU
- 10K samples in ~15 minutes
- Session limits: 12 hours
- Perfect for experiments!

**Vast.ai (Cheapest):**
- RTX 3080: $0.20-0.40/hour
- RTX 4090: $0.50-0.80/hour
- Good for serious training

---

## Troubleshooting

### Model won't load

```python
# Try explicit CPU loading
import torch
checkpoint = torch.load('model.pt', map_location='cpu')
```

### Different results on different machines

Normal - slight floating-point differences between CPUs/GPUs. Use:
```python
# For reproducibility
import torch
torch.manual_seed(42)
np.random.seed(42)
```

### Model file too large

225KB is tiny! But if needed:
```python
# Compress
import gzip
with open('model.pt', 'rb') as f_in:
    with gzip.open('model.pt.gz', 'wb') as f_out:
        f_out.writelines(f_in)
```

---

## Best Practices

### 1. Version Control

```bash
# Tag model versions
git tag -a v1.0-model -m "First production model"
git push --tags

# Store in Git LFS
git lfs track "*.pt"
git add .gitattributes *.pt
git commit -m "Add trained models"
```

### 2. Model Metadata

Create `model_metadata.json`:
```json
{
  "version": "v2.0",
  "created": "2024-10-05T03:20:00Z",
  "training_samples": 4620,
  "training_period": "2015-2024",
  "val_mae": 25.78,
  "test_correlation": 0.158,
  "features": ["macroeconomic", "fundamentals", "momentum"],
  "git_commit": "abc123",
  "trained_on": "MacBook Air M1",
  "duration_minutes": 48
}
```

### 3. A/B Testing

```python
# Compare models in production
models = {
    'v1': NeuralNetworkValuationModel(model_path='v1_model.pt'),
    'v2': NeuralNetworkValuationModel(model_path='v2_model.pt')
}

# Route 50% traffic to each
import random
model = models['v1' if random.random() < 0.5 else 'v2']
```

---

## Quick Commands

```bash
# Package for training
./scripts/package_for_training.sh

# Train locally
uv run python models/neural_network/training/comprehensive_neural_training.py

# Evaluate model
uv run python scripts/neural_network_evaluator.py

# Check progress
tail -f comprehensive_training.log | grep -E '(Epoch|MAE|Collected)'

# Compare models
ls -lh *.pt

# Test model
uv run python -c "
from pathlib import Path
from src.invest.valuation.neural_network_model import NeuralNetworkValuationModel
m = NeuralNetworkValuationModel(model_path=Path('trained_nn_2year_comprehensive.pt'))
print('✓ Model loads successfully')
"
```

---

## Summary

**You now have:**
1. ✅ Improved model with macro features
2. ✅ Better training data (2015-2024)
3. ✅ Enhanced confidence scoring
4. ✅ Portable training setup
5. ✅ Transfer documentation

**Next steps:**
1. Package for transfer: `./scripts/package_for_training.sh`
2. Train on powerful machine (GPU recommended)
3. Transfer models back
4. Compare with current model
5. Deploy best performer

**Files to reference:**
- This guide: `MODEL_MANAGEMENT.md`
- Training guide: `docs/portable_training_guide.md`
- Evaluation guide: `docs/neural_network_evaluation_guide.md`
