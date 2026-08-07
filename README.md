# Systematic Investment Analysis Framework

A configuration-driven, objective approach to investment analysis that eliminates conversational bias and provides consistent, reproducible results.

## Philosophy

This framework is designed to be:
- **Systematic**: Every stock goes through identical analysis steps
- **Objective**: No conversational AI bias - same inputs always produce same outputs  
- **Configurable**: Define your investment criteria in YAML files
- **Reproducible**: Identical methodology applied consistently
- **Comprehensive**: Quality → Value → Growth → Risk → Valuation pipeline

## Quick Start

⚠️ **IMPORTANT: Always use `uv run` for all commands** - This project uses uv dependency management.

### Database Setup

Everything reads and writes PostgreSQL, so create the database before running anything
else. Without this step the first command fails on a connection error.

```bash
# 1. Create the database and a user for it
createdb invest
psql invest -c "CREATE USER invest WITH PASSWORD 'choose-your-own-password';"
psql invest -c "GRANT ALL PRIVILEGES ON DATABASE invest TO invest;"

# 2. Load the schema (20 tables: assets, price_history, valuation_results, ...)
psql invest -f scripts/create_postgres_schema.sql

# 3. Tell the code how to connect, using the password chosen above
echo 'postgresql://invest:choose-your-own-password@localhost:5432/invest' > ~/.invest_db_url
```

`DB_URL` in the environment takes precedence over `~/.invest_db_url` if both are set.
Neither has a default — the code raises a message naming both options rather than
guessing a host and password. Reaching a database on another machine over an SSH
tunnel usually means port 5433 instead of 5432.

The database starts empty. Populate it with `uv run python scripts/update_all.py`,
which fetches prices and fundamentals from Yahoo Finance and SEC EDGAR.

### Using Claude Code

The easiest way to run the full pipeline (data fetch, valuations, dashboard):

```
/update_db                     # Refresh prices, run models, launch dashboard
/update_db --skip-fetch        # Re-run models on existing data
/update_db --universe europe   # Different universe
/brief                         # Portfolio intelligence — sell signals, buy opportunities
/research TICKER               # Deep dive one company — news, scenarios, verdict
```

`/update_db` fetches data, runs all models (GBM + classic valuations), generates the dashboard, and starts a live server at http://localhost:8080.

### Position Sizing

There is no automated position sizer. The Kelly-Criterion sizer was removed 2026-07-07 as mis-specified (it produced raw single-name bet fractions of 66-84% for nearly every stock, which the 15% cap silently clipped). Size positions by conviction under fixed rules: 15% single-name cap, 35% sector cap, event risk (earnings) handled manually. Read the raw model upside from the `valuation_results` table (AutoResearch first, then GBM) rather than a formula.

### Manual Commands

```bash
# Install dependencies with uv
uv sync

# Run with default conservative value screen
uv run systematic-invest

# Use specific configuration
uv run systematic-invest dashboard/configs/aggressive_growth.yaml

# International markets (Warren Buffett's Japanese favorites)
uv run python scripts/systematic_analysis.py dashboard/configs/japan_buffett_favorites.yaml --save-csv

# Alternative: Direct script execution (also requires uv run)
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_top100.yaml --save-csv

# List available configurations
uv run systematic-invest --list-configs

# Save results in multiple formats
uv run systematic-invest --save-csv --save-json --output results/
```

### CPU / GPU Torch

Torch is optional. Install one of the extras:

```bash
# CPU-only
uv sync --extra cpu

# GPU (CUDA) - replace cu118 if your CUDA version differs
uv sync --extra gpu --default-index https://download.pytorch.org/whl/cu118 --index https://pypi.org/simple
```

Choose the CUDA index (cu118, cu126, cu128, etc.) from the PyTorch install page.

### Docs (Local)

Docs: https://rubenayla.github.io/invest-engine/

```bash
uv run mkdocs serve
# open http://localhost:8000
```

### Static HTML Dashboard

View your investment analysis in a clean, fast static HTML dashboard:

```bash
# Generate/update the dashboard
uv run python scripts/dashboard.py

# Then open in browser
open dashboard/valuation_dashboard.html
```

**Dashboard Features:**
- 📊 **Multiple Valuation Models**: DCF, Enhanced DCF, Growth DCF, RIM, Simple Ratios, Neural Network predictions
- 🎯 **Interactive Sorting**: Click any column header to sort stocks
- 📈 **Real-Time Prices**: Current market prices with margin of safety calculations
- 🌐 **Multiple Universes**: S&P 500, Tech, Growth, International stocks
- 🎯 **Professional UI**: Clean, responsive design - no server needed!
- ⚡ **Fast Loading**: Static HTML loads instantly

### Full S&P 500 Analysis

To analyze ALL S&P 500 stocks (takes 10-15 minutes):

```bash
# Run full S&P 500 analysis with CSV output
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv

# Run quietly in background (no progress output)
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv --quiet &

# Check progress (if running in background)
tail -f sp500_full_screen_*_report.txt
```

**Note**: The full S&P 500 analysis fetches data for 500+ stocks and can take 10-15 minutes. The resulting CSV will include ALL stocks with a `Passes_Filters` column indicating whether each stock meets the screening criteria.

## How It Works

The framework uses a systematic, 5-step analysis pipeline:

1. **Quality Assessment** - Financial strength and stability
2. **Value Analysis** - Valuation attractiveness 
3. **Growth Evaluation** - Business expansion prospects
4. **Risk Assessment** - Financial and business risks
5. **Valuation Models** - DCF and RIM intrinsic value calculations

All analysis parameters are defined in YAML configuration files, ensuring consistent and reproducible results.

## Available Configurations

The framework includes several pre-built strategies:
- Conservative value investing
- Aggressive growth focus
- Full S&P 500 screening
- Custom sector analysis

All configurations can be customized to match your investment criteria.

## Deep Company Analysis

For individual stock deep dives (beyond the scanner), use the analysis methodology:

```
/research TICKER                                # Run via Claude command
.claude/commands/research.md                    # The methodology
```

The command writes one analysis file per company and maintains a ranked
watchlist. Point it at any notes directory you like (this repository holds
code only; set `INVEST_NOTES_DIR` for the dashboard's notes features).

The methodology covers: news/situation research, variant perception (Steinhardt), financial verification, business quality scoring, model triangulation, inflection point detection, scenario analysis, and setup/timing assessment.

## Project Structure

```
src/invest/              # Python package (analysis, data, valuation, screening)
scripts/                 # Runnable scripts (fetchers, predictors, dashboard)
tests/                   # Tests

models/                  # ML model code
├── autoresearch/        #   5-model ensemble predicting peak 2yr returns
├── neural_network/      #   LSTM/Transformer + GBM training & models
└── backtesting/         #   Strategy backtesting framework

data/                    # SQLite database + raw data
dashboard/               # HTML dashboard + scanner YAML configs
docs/                    # MkDocs documentation site
infra/                   # Infrastructure (Grafana)
logs/                    # Runtime logs
```

Research notes (company analyses, theses, watchlist) live outside this
repository — keep yours anywhere and point the tools at them with
`INVEST_NOTES_DIR`.

## Output Formats

Multiple output formats for different use cases:
- **Text Reports** - Human-readable analysis summaries
- **CSV Export** - Structured data for spreadsheet analysis
- **JSON Export** - Raw data for API integration

## Key Features

- **Systematic & Objective** - Eliminates human bias through consistent methodology
- **AI-Powered Predictions** - LSTM/Transformer neural network with 78.64% hit rate and 44.2% correlation
- **Static HTML Dashboard** - Fast, clean interface with real-time valuations - no server needed
- **Configurable** - Customize all screening criteria via YAML files
- **Comprehensive** - Analyzes quality, value, growth, and risk dimensions
- **Scalable** - Handle individual stocks or entire market indices
- **Professional Output** - Multiple export formats with detailed reporting

### Neural Network Model

The framework includes a production-ready LSTM/Transformer hybrid model for stock predictions:

- **Performance**: 78.64% directional accuracy, 44.2% correlation, 23.05% MAE
- **Training Data**: 3,534 snapshots (2006-2023), 92-100% feature coverage
- **Architecture**: Single-horizon (1-year) predictions with Monte Carlo Dropout for confidence
- **Database**: 1.4GB SQLite with complete fundamental data

For historical context and notes, see `stuff.md`.

## Usage Examples

⚠️ **Remember: All commands must use `uv run`**

```bash
# Run basic analysis
uv run python scripts/systematic_analysis.py

# Full S&P 500 analysis with CSV output
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv

# Custom configuration with multiple output formats
uv run python scripts/systematic_analysis.py dashboard/configs/my_strategy.yaml --save-csv --save-json
```

## Extending the Framework

The framework is designed for extensibility:
- Add new screening criteria
- Integrate additional data sources
- Implement custom valuation models
- Create sector-specific analysis modules

See the [Developer Guide](https://your-username.github.io/invest-engine/developer-guide/architecture/) for detailed extension instructions.

## Documentation

Comprehensive documentation is available at [rubenayla.github.io/invest-engine](https://rubenayla.github.io/invest-engine).

### Local Documentation

Run the documentation locally:

```bash
# Install documentation dependencies
uv sync --group docs

# Start documentation server
uv run mkdocs serve
```

Then visit http://localhost:8000

### Deploy Documentation

Deploy to GitHub Pages:

```bash
# Deploy to GitHub Pages
uv run mkdocs gh-deploy
```

## Testing

⚠️ **All test commands require `uv run`**

```bash
# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_systematic_analysis.py
```

## Dependencies

- **Python 3.12+**
- **yfinance** - Stock data and financials
- **pandas** - Data manipulation  
- **pydantic** - Configuration validation
- **pyyaml** - Configuration file parsing

## Limitations

- Currently uses Yahoo Finance (free but limited)
- Valuation model integration is preliminary
- International stock coverage limited
- No real-time data updates

## Why Systematic Analysis?

This framework addresses common issues in investment research:
- **Eliminates bias** - Consistent methodology for all stocks
- **Ensures completeness** - All relevant factors evaluated
- **Provides reproducibility** - Same inputs always yield same outputs
- **Creates audit trail** - Clear, documented analysis process

Ideal for investors seeking disciplined, objective stock analysis.

---

## Related Projects

- [investV2](https://github.com/albertorblan06/investV2) — C++20 quant trading terminal for Apple Silicon with real-time WebSocket feeds, on-device LLM sentiment (Qwen2-0.5B), XGBoost+LSTM ensemble, and GPU Monte Carlo. Complementary to this repo: they focus on real-time signals/execution, we focus on fundamental analysis/valuation.

## Original References

- [TIKR](https://app.tikr.com/markets?fid=1)
- [Finviz](https://finviz.com/)
- [Investing.com](https://www.investing.com/)
- [MacroTrends](https://www.macrotrends.net/)
- [Yahoo Finance](https://finance.yahoo.com/)
- [YCharts](https://ycharts.com/)
- [Simply Wall St](https://simplywall.st/)
- [Stock Analysis](https://stockanalysis.com/)

### Recommended Brokers
- **IBKR**: Interactive Brokers - Complex but low cost, extensive, app works well
- **TD Ameritrade** - Easy to use and 0 fees in US
- **Charles Schwab**
- **Fidelity Investments**
- **E*TRADE**
