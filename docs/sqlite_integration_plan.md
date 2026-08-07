# SQLite Integration Plan

## Goal
Consolidate all data storage into a single SQLite database, using JSON files only as backups.

## Current State

### Existing Database: `models/neural_network/training/stock_data.db` (1.2GB)
- **assets**: 103 stocks
- **snapshots**: 3,367 historical snapshots (up to 2022-11-30)
- **forward_returns**: Training labels for ML
- **price_history**: Historical price data
- **company_info**: Company metadata
- **models**: Model registry
- **valuation_predictions**: Classic valuation results
- **nn_predictions**: Neural network predictions

### Current JSON Files
- **data/stock_cache/*.json**: 436 files, raw yfinance data
- **dashboard/dashboard_data.json**: 2.3MB, predictions + valuations

## Proposed Schema Changes

### 1. New Table: `current_stock_data`
Store the latest fetched data for each stock (replaces JSON cache).

```sql
CREATE TABLE IF NOT EXISTS current_stock_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL UNIQUE,

    -- Basic info
    current_price REAL,
    market_cap REAL,
    sector TEXT,
    industry TEXT,
    long_name TEXT,
    short_name TEXT,
    currency TEXT,
    exchange TEXT,
    country TEXT,

    -- Financial metrics (from 'financials' section)
    trailing_pe REAL,
    forward_pe REAL,
    price_to_book REAL,
    return_on_equity REAL,
    debt_to_equity REAL,
    current_ratio REAL,
    revenue_growth REAL,
    earnings_growth REAL,
    operating_margins REAL,
    profit_margins REAL,
    total_revenue REAL,
    total_cash REAL,
    total_debt REAL,
    shares_outstanding REAL,
    trailing_eps REAL,
    book_value REAL,
    revenue_per_share REAL,
    price_to_sales_ttm REAL,

    -- Price data
    price_52w_high REAL,
    price_52w_low REAL,
    avg_volume INTEGER,
    price_trend_30d REAL,

    -- Raw JSON storage (for complex data)
    cashflow_json TEXT,  -- JSON string
    balance_sheet_json TEXT,  -- JSON string
    income_json TEXT,  -- JSON string

    -- Metadata
    fetch_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ticker)
);

CREATE INDEX idx_current_ticker ON current_stock_data(ticker);
CREATE INDEX idx_current_updated ON current_stock_data(last_updated);
```

### 2. Update Existing Table: `valuation_predictions`
Add more fields for classic models.

```sql
-- Already exists, verify it has:
-- id, model_id, ticker, prediction_date, current_price,
-- fair_value, upside, margin_of_safety, confidence, suitable, details_json
```

### 3. Update Existing Table: `nn_predictions`
Already has multi-horizon support.

```sql
-- Already exists, verify it has:
-- id, model_id, ticker, prediction_date, horizon,
-- predicted_return, fair_value, confidence, feature_vector_json, details_json
```

## Migration Strategy

### Phase 1: Add current_stock_data table
1. Create the new table
2. Migrate existing JSON cache to SQLite
3. Keep JSON files as backup

### Phase 2: Update data_fetcher.py
1. Write to SQLite first
2. Also write JSON backup
3. Add `--sqlite-only` flag for future

### Phase 3: Update readers
1. `run_multi_horizon_predictions.py` - read from SQLite
2. `run_classic_valuations.py` - read from SQLite
3. `dashboard.py` - read from SQLite

### Phase 4: Testing
1. Run full workflow with SQLite
2. Verify predictions match
3. Compare with JSON backups

### Phase 5: Cleanup (future)
1. Add flag to disable JSON backups
2. Eventually delete JSON files

## Implementation Order

1. ✅ Design schema (this document)
2. Create `current_stock_data` table
3. Write migration script to populate from JSON
4. Update `data_fetcher.py` to write to SQLite
5. Update all readers to use SQLite
6. Test complete workflow
7. Document the transition
