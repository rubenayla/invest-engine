# Static Dashboard

The valuation dashboard is a single static HTML file that renders all recently generated analysis results. No web server or background process is required—open the file in your browser once the data has been refreshed.

## Quick Start

```bash
# 1. Run your preferred analysis pipeline (examples)
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv

# 2. Regenerate the dashboard HTML from the SQLite results database
uv run python scripts/dashboard.py

# 3. View the dashboard (macOS example)
open dashboard/valuation_dashboard.html
```

The generator script collects the latest valuations from `data/stock_data.db`, renders the HTML, and writes `dashboard/valuation_dashboard.html`. You can host the file anywhere or open it locally.

## Updating Data

1. **Collect data** – run your normal fetching pipeline (for example `scripts/data_fetcher.py` if you maintain a cache).
2. **Produce valuations** – execute analysis jobs such as `scripts/systematic_analysis.py` or `scripts/offline_analyzer.py --update-dashboard` to populate the SQLite tables.
3. **Regenerate HTML** – run `uv run python scripts/dashboard.py`.
4. **Open the dashboard** – refresh the file in your browser to see the latest results.

Repeat steps 2–4 whenever you update valuations. The HTML generator is idempotent and overwrites the existing file each time.

## Dashboard Features

- 📊 **Multiple Valuation Models** – DCF variations, Residual Income, GBM machine learning models, and consensus outputs.
- 🎯 **Interactive Sorting** – Click any column header to sort within the browser.
- 📈 **Current Pricing** – Displays the latest prices alongside intrinsic value estimates and margin of safety calculations.
- 🌐 **Universe Support** – Works with every universe you analyze; the HTML reflects whatever is stored in the database.
- ⚡ **Fast Loading** – Static assets only; no runtime dependencies.
- 📚 **Model Documentation** – Direct link to comprehensive model documentation for understanding how each model works.

## Layout Overview

- **Header** – Shows last-updated metadata, stock counts, and helpful command references.
- **Valuation Table** – Main grid with tickers, pricing, upside/downside, and per-model valuations.
- **Details & Tooltips** – Hover to reveal confidence levels, error messages for unsuitable models, and methodology guidance.
- **Footer** – Quick reminders for regenerating analysis and keeping data fresh.

## Troubleshooting

- **Empty Dashboard** – Ensure the SQLite database contains `current_stock_data` and `valuation_results`. Re-run your analysis pipeline if tables are empty.
- **Stale Results** – Regenerate the dashboard after every analysis run; the HTML does not auto-refresh.
- **Different Machines** – Copy `dashboard/valuation_dashboard.html` and open it on any machine. No additional setup is required.

With the server-based dashboard removed, this static flow is now the single source of truth for sharing and reviewing valuation results.
