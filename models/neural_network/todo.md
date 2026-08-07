# Neural Network Improvements TODO

## Current Performance Baseline

### ✅ Latest Results (Mac - Smart Sampling)
- **Correlation**: **0.536 (53.6%)** - 🔥 EXCELLENT!
- **Improvement**: +239% from previous baseline (15.8% → 53.6%)
- **Architecture**: 3-layer network (input → 2 hidden → output)
- **Hidden layers**: 64-128 neurons
- **Training samples**: 198 (hit API rate limit)
- **Training time**: 6 minutes
- **Val MAE**: 23.94

### Previous Baseline (Before Smart Sampling)
- **Correlation**: 0.158 (15.8%) - weak predictive power
- **Train loss**: 839.9 < **Val loss**: 954.3 (underfitting)

## Architecture Experiments to Try

### 1. Deeper Networks
- [ ] 4-layer network (3 hidden layers)
- [ ] 5-layer network (4 hidden layers)
- [ ] 6+ layer network with residual connections

### 2. Wider Networks
- [ ] Increase neurons: 128-256-128
- [ ] Increase neurons: 256-512-256
- [ ] Increase neurons: 512-1024-512

### 3. Advanced Architectures
- [ ] Residual connections (skip connections between layers)
- [ ] Attention mechanisms for feature importance
- [ ] Multi-head architecture (separate heads for different time horizons)
- [ ] Ensemble of multiple architectures

### 4. Regularization Techniques
- [ ] L1/L2 regularization (current: basic dropout only)
- [ ] Batch normalization between layers
- [ ] Layer normalization
- [ ] Gradient clipping

### 5. Input Feature Engineering
- [ ] Add sector/industry one-hot encoding (from yfinance)
- [ ] Technical indicators (RSI, MACD, Bollinger Bands)
- [ ] Momentum features (price trends, volume trends)
- [ ] Relative valuation (compare to sector averages)
- [ ] News sentiment scores
- [ ] Insider trading activity

## Training Improvements

### 6. Data Collection
- [x] Smart stock sampling (use all stocks in their trading periods)
- [ ] Add more recent data (currently 2004-2024, focus 2015-2024)
- [ ] Increase sample size (currently 5000, try 10k, 20k)
- [ ] Balance samples across sectors
- [ ] Balance samples across market conditions (bull/bear markets)

### 7. Loss Functions & Objectives
- [ ] Try different loss functions (Huber loss, quantile loss)
- [ ] Multi-task learning (predict multiple time horizons simultaneously)
- [ ] Ranking loss (focus on relative ordering, not absolute values)
- [ ] Directional accuracy loss (predict up/down, not exact return)

### 8. Training Strategies
- [ ] Learning rate scheduling (cosine annealing, ReduceLROnPlateau)
- [ ] Cyclic learning rates
- [ ] Gradient accumulation for larger effective batch sizes
- [ ] Mixed precision training (faster on GPU)

## Evaluation & Analysis

### 9. Model Comparison Framework
- [ ] Compare NN vs DCF on same stocks
- [ ] Compare NN vs Graham Screen on same stocks
- [ ] Compare NN vs PEG ratio on same stocks
- [ ] Ensemble: Combine NN with fundamentals-based models

### 10. Confidence Metrics
- [ ] Implement prediction uncertainty (Monte Carlo dropout)
- [ ] Use NN when high confidence, fundamentals otherwise
- [ ] Calibrate confidence scores with actual performance
- [ ] Report prediction intervals (e.g., 80% confidence bounds)

### 11. Performance Analysis
- [ ] Per-sector performance breakdown
- [ ] Performance by market cap
- [ ] Performance by market conditions (bull/bear)
- [ ] Analyze failure cases (when NN is very wrong)
- [ ] Feature importance analysis (which inputs matter most)

## Next Steps (Priority Order)

### Immediate (Current Session)
1. **✅ DONE: Smart sampling** - Achieved 53.6% correlation (was 15.8%)!
2. **⏳ Wait for Windows GPU training** - ETA ~23 minutes (5000 samples, 2004-2024)
3. **Generate training cache** - Run training once to create cache file for fast iteration
4. **Test cache system** - Verify cache loads correctly on second run

### Architecture Experiments (After Cache is Ready)
4. **Try deeper network** - 4-5 layers to see if we can exceed 53.6%
5. **Try wider network** - 256-512-256 neurons
6. **Add batch normalization** - Between layers for stability
7. **Add sector encoding** - Include industry information from yfinance

### Model Integration
8. **Model comparison framework** - Compare NN vs DCF/Graham/PEG on same stocks
9. **Ensemble approach** - Combine NN with fundamentals when NN has low confidence
10. **Confidence metrics** - Implement prediction uncertainty (Monte Carlo dropout)

## Success Criteria

- **Good performance**: Correlation > 0.30 (30%)
- **Excellent performance**: Correlation > 0.50 (50%)
- **Production ready**: Consistent performance across sectors and time periods
