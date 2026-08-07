# Grafana Dashboard for Investment Analysis

This directory contains the configuration to run a local Grafana instance connected to your SQLite database.

## Quick Start

1.  **Start Grafana:**
    ```bash
    docker-compose up -d
    ```

2.  **Open Grafana:**
    *   Go to [http://localhost:3000](http://localhost:3000)
    *   **Username:** `admin`
    *   **Password:** `admin`

3.  **Explore Data:**
    *   Go to **Explore** (compass icon).
    *   Ensure "Invest SQLite" is selected as the datasource.
    *   Try running a query (see below).

## Data Source

The `stock_data.db` is automatically connected.
*   **Path:** `/var/lib/grafana/data/stock_data.db` (inside container)
*   **Type:** SQLite (via `frser-sqlite-datasource` plugin)

## Useful Queries

### 1. Top 20 Undervalued Stocks (High Confidence)
```sql
SELECT
  ticker,
  current_price,
  fair_value,
  upside_pct,
  confidence
FROM valuation_results
WHERE suitable = 1 AND confidence > 0.6
ORDER BY upside_pct DESC
LIMIT 20
```

### 2. Average Upside by Sector
```sql
SELECT
  c.sector,
  AVG(v.upside_pct) as avg_upside,
  COUNT(*) as stock_count
FROM valuation_results v
JOIN current_stock_data c ON v.ticker = c.ticker
WHERE v.suitable = 1
GROUP BY c.sector
ORDER BY avg_upside DESC
```

### 3. Price vs Fair Value (Time Series)
*Note: This requires historical entries in `valuation_results`. If you only have the latest snapshot, this will show points.*

```sql
SELECT
  timestamp as time,
  fair_value
FROM valuation_results
WHERE ticker = 'AAPL' AND model_name = 'single_horizon_nn'
ORDER BY timestamp ASC
```

## Troubleshooting

*   **Database Locked:** The database is mounted as Read-Only (`:ro`) to preventing Grafana from locking it while your scripts are running. You can run your analysis scripts (`scripts/offline_analyzer.py`) without stopping Grafana.
*   **Missing Data:** If tables are empty, run your data fetcher and analyzer scripts first:
    ```bash
    uv run python scripts/data_fetcher.py --universe sp500 --max-stocks 50
    uv run python scripts/offline_analyzer.py --universe cached --update-dashboard
    ```
