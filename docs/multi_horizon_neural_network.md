# Multi-Horizon Neural Network Valuation Model

## Overview

The Multi-Horizon Neural Network is an advanced machine learning model that predicts stock performance across **5 different time horizons simultaneously** using a single neural network with multiple output neurons. This approach addresses the fundamental challenge: "Is a stock good for next month or next 5 years?"

## Key Innovation: Multi-Output Architecture

### The Problem
Traditional models predict a single timeframe:
- Short-term models (1 month) miss long-term value
- Long-term models (5 years) miss trading opportunities
- Training 5 separate models is inefficient and inconsistent

### The Solution
**One model, 5 outputs** - A single neural network with 5 output neurons, each predicting a different time horizon:

```python
Input Layer (60+ features)
    ↓
Dense(256) + BatchNorm + ReLU + Dropout(0.3)
    ↓
Dense(128) + BatchNorm + ReLU + Dropout(0.3)
    ↓
Dense(64) + BatchNorm + ReLU + Dropout(0.3)
    ↓
Dense(32) + BatchNorm + ReLU + Dropout(0.3)
    ↓
Dense(5 outputs) ← 1m, 3m, 6m, 1y, 2y predictions
```

## Five Time Horizons

| Horizon | Use Case | Dashboard Column |
|---------|----------|------------------|
| **1 month** | Short-term trading, swing trades | NN 1m |
| **3 months** | Quarterly earnings plays | NN 3m |
| **6 months** | Medium-term positions | NN 6m |
| **1 year** | Standard investment horizon | NN 1y |
| **2 years** | Long-term value investing | NN 2y |

## Features

### Input Features (60+)

#### Valuation Ratios
- P/E, Forward P/E, PEG ratio
- Price-to-Book, Price-to-Sales
- EV/EBITDA, EV/Revenue

#### Profitability Metrics
- ROE, ROA, ROIC
- Profit margins (gross, operating, net)
- Operating margins

#### Growth Metrics
- Revenue growth (YoY, 3-year CAGR)
- Earnings growth (YoY, 3-year CAGR)
- Book value growth

#### Financial Health
- Current ratio, Quick ratio
- Debt-to-Equity ratio
- Interest coverage
- Cash-to-Debt ratio

#### Market Metrics
- Beta (market volatility)
- Market cap (log-scaled for normalization)
- Trading volume patterns
- 52-week high/low ratios

#### Momentum Indicators
- Distance from 52-week high/low
- Moving average convergence
- Price trends

#### Sector Context
- **Sector encoding** (one-hot or learned embeddings)
- Industry-relative metrics
- Sector-adjusted valuations

### Feature Engineering

1. **Ratio-based features** (scale-invariant)
2. **Log-transformation** for absolute values (market cap, volume)
3. **Robust scaling** to handle outliers (uses median, IQR instead of mean, std)
4. **Missing value handling** with intelligent defaults

## Data Storage and Cache

### SQLite Database Architecture

**Location**: `models/neural_network/training/stock_data.db` (1.2GB)

#### Main Table: `current_stock_data`

```sql
CREATE TABLE current_stock_data (
    id INTEGER PRIMARY KEY,
    ticker TEXT UNIQUE NOT NULL,

    -- Basic info
    current_price REAL,
    market_cap REAL,
    sector TEXT,
    industry TEXT,

    -- Financial ratios (extracted for quick access)
    trailing_pe REAL,
    forward_pe REAL,
    price_to_book REAL,
    return_on_equity REAL,
    debt_to_equity REAL,
    current_ratio REAL,

    -- Growth metrics
    revenue_growth REAL,
    earnings_growth REAL,
    operating_margins REAL,
    profit_margins REAL,

    -- Fundamental data
    trailing_eps REAL,
    book_value REAL,
    total_cash REAL,
    total_debt REAL,
    shares_outstanding REAL,

    -- JSON blobs for complex data
    cashflow_json TEXT,  -- Historical cash flow statements
    balance_sheet_json TEXT,  -- Historical balance sheets
    income_json TEXT,  -- Historical income statements
    info_data TEXT,  -- Full yfinance info dict
    financials_data TEXT,  -- Additional financial metrics

    -- Metadata
    fetch_timestamp TEXT,
    last_updated TEXT
);
```

### Data Flow

```
yfinance API
    ↓
data_fetcher.py
    ↓
SQLite Database (primary)
    ↓
StockDataReader
    ↓
Neural Network Model
    ↓
5 Predictions (1m, 3m, 6m, 1y, 2y)
    ↓
Dashboard Display
```

### Cache Design

#### Why SQLite Over JSON?

**Before** (JSON cache):
- 436 files × 40KB = 17MB
- No indexing
- No query capability
- Prone to corruption
- Race conditions during writes

**After** (SQLite):
- Single 1.2GB database file
- Indexed queries
- Atomic transactions
- ACID compliance
- Can query by sector, date, metrics

#### StockDataReader Module

Location: `src/invest/data/stock_data_reader.py`

```python
from invest.data.stock_data_reader import StockDataReader

# Initialize reader
reader = StockDataReader()

# Get single stock (returns dict compatible with models)
data = reader.get_stock_data('AAPL')
# Returns: {
#     'info': {...},          # Includes critical fields for models
#     'financials': {...},    # Performance metrics
#     'cashflow': [...],      # Historical cash flows (as DataFrame)
#     'balance_sheet': [...], # Historical balance sheets
#     'income': [...]         # Historical income statements
# }

# List all tickers
tickers = reader.get_all_tickers()  # ['AAPL', 'MSFT', ...]

# Filter by sector
tech_stocks = reader.get_stocks_by_sector('Technology')

# Get count
total = reader.get_stock_count()  # 435
```

#### Critical Data Structure

**IMPORTANT**: The `StockDataReader` puts critical fields in **BOTH** `info` and `financials` sections:

```python
data['info'] = {
    # Basic company info
    'currentPrice': 243.42,
    'sector': 'Technology',
    'longName': 'Apple Inc.',

    # CRITICAL: These are duplicated from 'financials'
    # for compatibility with traditional models
    'sharesOutstanding': 15000000000,
    'totalCash': 50000000000,
    'totalDebt': 100000000000,
    'trailingEps': 6.5,
    'bookValue': 3.5,
    'freeCashflow': 90000000000,      # Extracted from cashflow_json
    'operatingCashflow': 100000000000  # Extracted from cashflow_json
}

data['financials'] = {
    # Same critical fields (for neural network models)
    'sharesOutstanding': 15000000000,
    'totalCash': 50000000000,
    # ... plus additional ratios
    'trailingPE': 34.5,
    'forwardPE': 32.1,
    'priceToBook': 65.2,
    # ...
}
```

**Why duplicate?**
- Traditional models (DCF, RIM, Simple Ratios) look in `info`
- Neural network models look in `financials`
- The split is **artificial** (historical design decision)
- Could be unified but would require updating all models

## Training Process

### Data Collection

1. **Historical snapshots** stored in `snapshots` table
2. **Forward returns** calculated and stored in `forward_returns` table
3. **Feature engineering** extracts 60+ features from each snapshot
4. **Train/validation/test split** (70/15/15)

### Training Pipeline

```bash
# Collect training data from database
uv run python models/neural_network/training/collect_training_data.py

# Train multi-horizon model
uv run python models/neural_network/training/train_multi_horizon.py \
    --epochs 100 \
    --batch-size 32 \
    --learning-rate 0.001

# Evaluate on test set
uv run python models/neural_network/training/evaluate_model.py
```

### Loss Function

**Huber Loss** (robust to outliers):
```python
loss = sum([huber_loss(pred_1m, actual_1m),
            huber_loss(pred_3m, actual_3m),
            huber_loss(pred_6m, actual_6m),
            huber_loss(pred_1y, actual_1y),
            huber_loss(pred_2y, actual_2y)]) / 5
```

### Regularization

- **Dropout**: 30% to prevent overfitting
- **Batch normalization**: Stable training
- **L2 weight decay**: 1e-5
- **Early stopping**: Patience of 10 epochs

## Running Predictions

### Generate Predictions for All Stocks

```bash
# Run multi-horizon predictions
uv run python scripts/run_multi_horizon_predictions.py

# Output: Predictions saved to database and dashboard_data.json
```

### Prediction Output Format

```python
{
    'ticker': 'AAPL',
    'predictions': {
        '1month': {
            'expected_return': 0.05,  # 5% predicted return
            'confidence': 0.82,       # 82% confidence
            'prediction_date': '2025-01-08'
        },
        '3month': {'expected_return': 0.08, 'confidence': 0.78},
        '6month': {'expected_return': 0.12, 'confidence': 0.75},
        '1year': {'expected_return': 0.18, 'confidence': 0.71},
        '2year': {'expected_return': 0.35, 'confidence': 0.65}
    }
}
```

## Dashboard Integration

### Display Format

The dashboard shows all 5 horizons in separate columns:

| Ticker | ... | NN 1m | NN 3m | NN 6m | NN 1y | NN 2y |
|--------|-----|-------|-------|-------|-------|-------|
| AAPL   | ... | 5.0% | 8.0% | 12.0% | 18.0% | 35.0% |
| VRSK   | ... | 2.7% | 3.9% | 5.2% | 8.1% | 15.5% |

Each cell shows:
- **Predicted return %** (color-coded: green if positive, red if negative)
- **Margin of safety** vs current price
- **Confidence level** (on hover)

### Color Coding

```python
if predicted_return >= 0.20:  # 20%+ upside
    color = "dark-green"
elif predicted_return >= 0.10:  # 10-20% upside
    color = "light-green"
elif predicted_return >= 0:  # 0-10% upside
    color = "yellow"
else:  # Negative return
    color = "red"
```

## Model Evaluation

### Metrics

1. **Mean Absolute Error (MAE)**: Average prediction error
2. **Root Mean Squared Error (RMSE)**: Penalizes large errors
3. **R² Score**: Explained variance (0-1, higher is better)
4. **Hit Rate**: % of predictions with correct direction
5. **Sharpe Ratio**: Risk-adjusted returns of predictions

### Confidence Estimation

```python
# Ensemble predictions with dropout enabled
predictions = []
for i in range(100):
    pred = model.predict(features, training=True)  # Dropout active
    predictions.append(pred)

mean_prediction = np.mean(predictions, axis=0)
std_prediction = np.std(predictions, axis=0)

# Confidence based on prediction variance
confidence = 1 - min(std_prediction / abs(mean_prediction), 1.0)
```

## Comparison with Traditional Models

### When Neural Network Outperforms

✅ **Stocks with complex patterns**
- Multiple growth phases
- Non-linear relationships
- Sector-specific dynamics

✅ **Feature-rich stocks**
- Complete financial data
- Long trading history
- Consistent reporting

### When Traditional Models Outperform

✅ **Simple, stable businesses**
- Utilities with predictable cash flows
- Mature dividend payers
- REITs with clear valuations

✅ **Limited data scenarios**
- IPOs, young companies
- Missing financial metrics
- Sparse trading history

## Future Improvements

### Short-term
1. ✅ Sector encoding (industry as input)
2. ⏳ Confidence intervals per prediction
3. ⏳ Separate test/train sets by decade and sector
4. ⏳ Ensemble with traditional models

### Long-term
1. ⏳ Transformer architecture for sequence modeling
2. ⏳ Multi-task learning (predict returns + volatility)
3. ⏳ Attention mechanisms to explain predictions
4. ⏳ Genetic algorithms for hyperparameter tuning

## Troubleshooting

### Model predicts identical values for all stocks

**Cause**: Features not being extracted correctly

**Solution**: Check that `StockDataReader` is merging `info` and `financials`:
```python
info = {**data.get('info', {}), **(data.get('financials') or {})}
```

### Predictions seem random

**Cause**: Model needs retraining or insufficient training data

**Solution**:
```bash
# Retrain with more data
uv run python models/neural_network/training/train_multi_horizon.py \
    --min-samples 10000 \
    --epochs 200
```

### Cache miss errors

**Cause**: Script looking for JSON files instead of SQLite

**Solution**: Update script to use `StockDataReader`:
```python
from invest.data.stock_data_reader import StockDataReader
reader = StockDataReader()
data = reader.get_stock_data(ticker)  # Not load_json_cache()
```

## References

- Original neural network model: `docs/neural_network_model.md`
- SQLite integration: `docs/sqlite_integration_complete.md`
- Training guide: `docs/portable_training_guide.md`
- Evaluation guide: `docs/neural_network_evaluation_guide.md`
