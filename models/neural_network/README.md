# Neural Network Stock Prediction System

## Overview

This neural network system predicts future stock returns based on fundamental financial metrics, ratios, and growth indicators. It's designed to complement traditional valuation models (DCF, Graham, PEG) by learning patterns from historical data.

## Current Performance

**Baseline (as of 2025-10-05)**:
- **Correlation**: 0.158 (15.8%) - weak predictive power
- **Architecture**: 3-layer network (input → 2 hidden → output)
- **Hidden layers**: 64-128 neurons
- **Model size**: ~224KB
- **Train loss**: 839.9 < **Val loss**: 954.3 (underfitting - can learn more)

## Directory Structure

```
models/neural_network/
├── models/              # Trained model files (*.pt)
├── training/           # Training scripts and results
│   ├── comprehensive_neural_training.py
│   ├── start_gpu_training.sh
│   └── comprehensive_training_results_*.json
├── docs/               # Documentation and planning
│   └── todo.md        # Improvement ideas and experiments to try
└── README.md          # This file
```

## Training

### Training Data Cache

The training script automatically caches collected historical data to avoid re-downloading on subsequent runs:

- **Cache location**: `models/neural_network/training/training_data_cache.json`
- **Auto-saves**: After collecting training data
- **Auto-loads**: On next run if config matches (start_year, end_year, target_samples)
- **Disable**: Set `use_cache=False` in `TrainingConfig`

This dramatically speeds up training iterations - **data collection can take hours**, but with cache it's instant!

### Local Training (Mac)
```bash
cd ~/repos/invest
uv run python models/neural_network/training/comprehensive_neural_training.py
```

### GPU Training (Windows WSL)
From Mac:
```bash
# Start training remotely
ssh ruben@192.168.1.117 'wsl bash -c "cd ~/repos/invest && setsid bash ./models/neural_network/training/start_gpu_training.sh > training.log 2>&1 < /dev/null &"'

# Check progress
ssh ruben@192.168.1.117 'wsl cat ~/repos/invest/comprehensive_training.log'

# Monitor GPU usage
ssh ruben@192.168.1.117 'wsl nvidia-smi'
```

See `WINDOWS_WSL_SETUP.md` in root for detailed Windows setup.

## Models

### Current Models (models/)
- `trained_nn_1month.pt` - 1-month forward return prediction
- `trained_nn_3month.pt` - 3-month forward return prediction
- `trained_nn_6month.pt` - 6-month forward return prediction
- `trained_nn_18month.pt` - 18-month forward return prediction
- `trained_nn_1year.pt` - 1-year forward return prediction
- `trained_nn_2year.pt` - 2-year forward return prediction
- `trained_nn_3year.pt` - 3-year forward return prediction
- `best_comprehensive_nn_2year_25epochs.pt` - Best 2-year model from comprehensive training

### Model Architecture
```python
StockPredictor(
  (fc1): Linear(in_features=15, out_features=64)
  (fc2): Linear(in_features=64, out_features=128)
  (fc3): Linear(in_features=128, out_features=1)
  (dropout): Dropout(p=0.2)
  (relu): ReLU()
)
```

**Input features (15)**:
- Price ratios: P/E, P/B, PEG
- Profitability: ROE, ROA, operating margin, gross margin
- Financial health: Debt-to-equity, current ratio
- Growth: Revenue growth, earnings growth, book value growth
- Valuation: Price-to-sales, price-to-FCF, EV/EBITDA

## Future Improvements

See `docs/todo.md` for comprehensive list of experiments to try, including:
- Deeper/wider architectures
- Feature engineering (sector encoding, technical indicators)
- Advanced training strategies
- Ensemble approaches

## Success Criteria

- **Good performance**: Correlation > 0.30 (30%)
- **Excellent performance**: Correlation > 0.50 (50%)
- **Production ready**: Consistent performance across sectors and time periods
