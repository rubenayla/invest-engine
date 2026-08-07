# Neural Network Valuation Model

## Overview

The Neural Network Valuation Model uses deep learning to predict stock valuations based on 60+ engineered features from fundamental financial data. It can be trained on historical market data to recognize patterns and relationships that traditional valuation models might miss.

## Key Features

### 1. Extensive Feature Engineering
- **Valuation Ratios**: P/E, Forward P/E, PEG, P/B, P/S, EV/EBITDA
- **Profitability Metrics**: ROE, ROA, ROIC, profit margins
- **Growth Metrics**: Revenue growth, earnings growth, 3-year trends
- **Financial Health**: Current ratio, debt/equity, interest coverage
- **Market Metrics**: Beta, market cap (log-scaled), volume
- **Momentum Indicators**: 52-week high/low ratios, moving averages
- **Analyst Sentiment**: Target prices, recommendations

### 2. Flexible Architecture
- Configurable hidden layers (default: 256→128→64→32)
- Dropout regularization (30% default)
- Batch normalization for stable training
- Support for different output types (score or expected return)

### 3. Time Horizon Support
- **1 month**: Short-term trading opportunities
- **1 year**: Standard investment horizon
- **5 years**: Long-term value investing

## Technical Implementation

### Data Normalization Strategy

The model uses a **hybrid approach** as recommended:

1. **Ratio-based features** are primary inputs (P/E, ROE, etc.)
2. **Log-transformed absolute values** for scale invariance
3. **Robust scaling** to handle outliers
4. **Sector-relative encoding** for industry context

### Neural Network Architecture

```python
Input Layer (60-80 features)
    ↓
Dense Layer (256 neurons) + BatchNorm + ReLU + Dropout
    ↓
Dense Layer (128 neurons) + BatchNorm + ReLU + Dropout
    ↓
Dense Layer (64 neurons) + BatchNorm + ReLU + Dropout
    ↓
Dense Layer (32 neurons) + BatchNorm + ReLU + Dropout
    ↓
Output Layer (1 neuron) + Sigmoid (for score output)
```

### Training Process

1. **Data Collection**: Historical financial data from multiple companies
2. **Feature Extraction**: Convert raw data to engineered features
3. **Target Generation**: Calculate actual returns over the target horizon
4. **Time Series Split**: Ensure no look-ahead bias
5. **Training**: Adam optimizer with MSE loss
6. **Validation**: Track performance on held-out data

## Usage Examples

### Basic Valuation
```python
from invest.valuation.model_registry import ModelRegistry

registry = ModelRegistry()
model = registry.get_model('neural_network')

# Requires a trained model file to be present in models/neural_network/models/
# Otherwise raises ValuationError
result = model.value_company('AAPL')
print(f'Fair Value: ${result.fair_value:.2f}')
print(f'Margin of Safety: {result.margin_of_safety:.1f}%')
```

### Training the Model
```python
from invest.valuation.neural_network_model import NeuralNetworkValuationModel

model = NeuralNetworkValuationModel(time_horizon='1year')

# Prepare training data
training_data = []
for ticker in ['AAPL', 'MSFT', 'GOOGL', ...]:
    data = fetch_financial_data(ticker)
    target_return = calculate_actual_return(ticker, '1year')
    training_data.append((ticker, data, target_return))

# Train the model
metrics = model.train_model(
    training_data,
    validation_split=0.2,
    epochs=100
)

# Save for later use
model.save_model('models/nn_1year.pt')
```

### Using a Pre-trained Model
```python
model = NeuralNetworkValuationModel(
    time_horizon='1year',
    model_path=Path('models/nn_1year.pt')
)

result = model.value_company('TSLA')
```

## Key Advantages

1. **Pattern Recognition**: Identifies complex relationships between financial metrics
2. **Adaptability**: Can be retrained as market conditions change
3. **Comprehensive Analysis**: Uses 60+ features vs 5-10 in traditional models
4. **Uncertainty Quantification**: Provides confidence scores via dropout inference

## Important Considerations

### When to Use
- Companies with comprehensive financial data
- When you have historical data for training
- As part of an ensemble with traditional models
- For pattern-based market analysis

### When NOT to Use
- Early-stage companies with limited data
- During unprecedented market conditions
- As the sole valuation method
- Without regular retraining

## Model Confidence Levels

The model provides three confidence levels:
- **High**: Low prediction uncertainty (<5% std dev)
- **Medium**: Moderate uncertainty (5-10% std dev)
- **Low**: High uncertainty (>10% std dev)

## Integration with Existing Models

The neural network model is fully integrated with:
- **Model Registry**: Available as 'neural_network'
- **Ensemble Model**: Can be included in weighted averages
- **Data Requirements**: Documented in model_requirements.py
- **Caching System**: Leverages cached API calls

## Performance Expectations

- Accuracy: Depends on training data quality and quantity
- Recommended: 1000+ training samples
- Retraining: Quarterly or when market regime changes

## Future Enhancements

1. **Automatic retraining** with scheduled updates
2. **SHAP values** for feature importance explanation
3. **Ensemble of networks** for different market conditions
4. **Transfer learning** from pre-trained financial models
5. **Real-time feature updates** with streaming data