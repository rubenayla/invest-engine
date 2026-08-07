# LSTM/Transformer Single-Horizon Stock Prediction Model

## Overview

A modern hybrid neural network architecture that predicts 1-year stock returns with statistical confidence intervals using MC Dropout.

**Key Innovation:** Combines the best of both worlds:
- **LSTM** for temporal patterns in historical fundamentals
- **Transformer attention** for feature importance
- **MC Dropout** for statistical uncertainty quantification

## Architecture

```
Temporal Features (4 snapshots × 11 features)
    ↓
LSTM(256) - 2 layers with dropout
    ↓
    │
    ├─────────────────────┐
    │                     │
    ↓                     ↓
Temporal Repr.      Static Features (22 features)
(256 dims)              ↓
    │             Dense(128) + BatchNorm + Dropout
    │                     ↓
    │              Static Repr. (128 dims)
    │                     │
    └─────────┬───────────┘
              ↓
        Concatenate (384 dims)
              ↓
    Transformer Encoder (2 layers, 8 heads)
              ↓
        Dense(128) → Dense(64) → Dense(1)
              ↓
        1-Year Return Prediction
```

## Features

### Temporal Features (11 per snapshot)
Extracted from sequence of 4 historical snapshots:

1. Market cap (log-transformed)
2. P/E ratio
3. Price-to-book ratio
4. Profit margins
5. Operating margins
6. Return on equity
7. Revenue growth
8. Earnings growth
9. Debt-to-equity
10. Current ratio
11. Free cash flow (log-transformed)

### Static Features (22 total)
Current snapshot + sector encoding:

**Valuation (2):** PE ratio, PB ratio

**Profitability (3):** Profit margins, operating margins, ROE

**Growth (2):** Revenue growth, earnings growth

**Financial Health (2):** Debt-to-equity, current ratio

**Market (2):** Beta, market cap (log)

**Sector One-Hot (11):** Technology, Healthcare, Financial Services, Consumer Cyclical, Industrials, Communication Services, Consumer Defensive, Energy, Utilities, Real Estate, Basic Materials

## MC Dropout Confidence Estimation

Unlike traditional models that give a single prediction, this model provides **statistical confidence intervals**:

```python
# Run model 100 times with dropout enabled
predictions = []
for _ in range(100):
    pred = model(features, training=True)  # Keep dropout ON
    predictions.append(pred)

# Calculate statistics
mean = np.mean(predictions)
std = np.std(predictions)

# 95% confidence interval
lower = mean - 2*std
upper = mean + 2*std
```

**Example Output:**
- **Prediction:** 15.0% 1-year return
- **95% CI:** [12.5%, 17.5%]
- **Std Dev:** 1.25%

**Interpretation:**
- Low std dev (< 2%) = High confidence, clear pattern
- High std dev (> 5%) = Low confidence, uncertain prediction

## Training Data

**Source:** Historical snapshots database (21 years, 2004-2025)

**Dataset:**
- 2,955 training samples from 103 large-cap stocks
- 2,068 training / 443 validation / 444 test
- Stratified split by decade and sector

**Features:**
- 3,367 point-in-time snapshots with fundamentals
- 8.5M daily price records
- 16,835 pre-calculated forward returns

**Target:** 1-year forward return (from `forward_returns` table)

## Training Configuration

```bash
uv run python models/neural_network/training/train_single_horizon.py \
    --epochs 100 \
    --batch-size 32 \
    --learning-rate 0.001
```

**Hyperparameters:**
- Loss: Huber Loss (robust to outliers)
- Optimizer: Adam with weight decay 1e-5
- Dropout: 30% (for MC Dropout sampling)
- Early stopping: Patience of 10 epochs
- LSTM hidden: 256 units
- Transformer: 2 layers, 8 attention heads

## Model Performance

**Training Metrics:**
- Train Loss: ~0.005 (converged)
- Val Loss: ~0.0001 (converged)
- Model saves best checkpoint based on validation loss

**Evaluation:** (To be completed after full training)
- Test set performance across decades
- Sector-specific accuracy
- Comparison with traditional DCF/RIM models

## Usage

### Making Predictions

```python
from invest.valuation.lstm_transformer_model import SingleHorizonModel
from invest.data.stock_data_reader import StockDataReader

# Initialize
model = SingleHorizonModel()
reader = StockDataReader()

# Load trained weights
model.model.load_state_dict(torch.load('best_model.pt'))

# Get stock data
data = reader.get_stock_data('AAPL')

# Predict with confidence
result = model.predict_with_confidence('AAPL', data, n_samples=100)

print(f"Expected 1-year return: {result.expected_return:.2%}")
print(f"95% confidence: [{result.confidence_lower:.2%}, {result.confidence_upper:.2%}]")
print(f"Fair value: ${result.fair_value:.2f}")
print(f"Current price: ${result.current_price:.2f}")
```

### Output Format

```python
PredictionResult(
    ticker='AAPL',
    expected_return=0.15,        # 15% expected return
    confidence_lower=0.125,      # Lower bound (12.5%)
    confidence_upper=0.175,      # Upper bound (17.5%)
    confidence_std=0.0125,       # Standard deviation
    current_price=150.0,
    fair_value=172.5,            # 150 * (1 + 0.15)
    margin_of_safety=0.15        # 15% upside
)
```

## Advantages Over Multi-Horizon Model

| Feature | Single-Horizon (This Model) | Multi-Horizon (Old) |
|---------|----------------------------|---------------------|
| **Predictions** | 1 output (1-year return) | 5 outputs (1m, 3m, 6m, 1y, 2y) |
| **Confidence** | MC Dropout (statistical) | Attention weights (learned) |
| **Evaluation** | "Is 1-year accurate?" | "Which horizon to trust?" |
| **Architecture** | LSTM + Transformer | Feedforward + Multi-head |
| **Training** | Simpler, faster convergence | Complex, 5 loss terms |

## Files

### Core Implementation
- `src/invest/valuation/lstm_transformer_model.py` - Main model architecture
- `src/invest/valuation/feature_extraction.py` - Feature extraction utilities
- `models/neural_network/training/train_single_horizon.py` - Training script

### Database
- `models/neural_network/training/stock_data.db` - Historical snapshots and returns
- Tables: `snapshots`, `price_history`, `forward_returns`, `assets`

### Trained Models
- `models/neural_network/training/best_model.pt` - Best model checkpoint

## Future Improvements

### Short-term
- [ ] Complete evaluation on test set
- [ ] Dashboard integration with confidence intervals
- [ ] Comparison study vs traditional models

### Long-term
- [ ] Add quarterly financial statements as temporal features
- [ ] Incorporate macroeconomic indicators
- [ ] Ensemble with traditional DCF/RIM models
- [ ] Real-time retraining pipeline

## References

Based on 2024 research consensus:
- Hybrid LSTM/Transformer architectures
- MC Dropout for uncertainty quantification
- Multi-stage feature extraction
- Sector-aware normalization

## Related Documentation

- [Multi-Horizon Neural Network](multi_horizon_neural_network.md) - Old 5-output model
- [SQLite Integration](sqlite_integration_complete.md) - Database architecture
- [Neural Network Evaluation](neural_network_evaluation_guide.md) - Performance metrics
