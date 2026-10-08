# Scripts

This folder contains the repo's runnable entrypoints (things we intentionally keep working).

## Core Entry Points
- `scripts/update_all.py` / `scripts/update_all.sh`: end-to-end pipeline
- `scripts/systematic_analysis.py`: run an analysis config from `dashboard/configs/*.yaml`
- `scripts/data_fetcher.py`: fetch/cache market + fundamentals into the local cache/SQLite
- `scripts/offline_analyzer.py`: analyze cached data and optionally update the dashboard
- `scripts/run_all_predictions.py`: orchestrate prediction jobs
- `scripts/run_gbm_predictions.py`: GBM predictions (all variants/horizons)
- `scripts/run_multi_horizon_predictions.py`: NN predictions (multi-horizon)
- `scripts/run_classic_valuations.py`: classic valuation models
- `scripts/run_opportunity_scan.py`: daily opportunity scan + notifications
- `scripts/dashboard.py`: regenerate HTML dashboard
- `scripts/update_price_history_current.py`: refresh `price_history` for `current_stock_data` tickers
- `scripts/update_macro_rates.py`: refresh risk-free rate series into `macro_rates`

## Setup / Ops
- `scripts/setup-githooks.sh`
- `scripts/package_for_training.sh`
- `scripts/receive_trained_models.sh`

## Private companies

`uv run private-companies` is the package entry point for schema setup, SEC Form D collection, reviewed imports, evidence checks and private Markdown dossiers. See [the module workflow](../src/invest/private_companies/README.md). `scripts/create_private_companies_schema.sql` creates separate tables in the existing PostgreSQL database.
