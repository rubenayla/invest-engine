# Backtesting Framework

Historical performance testing for the investment screening system to evaluate how your strategy would have performed in the past.

## Overview

This framework rigorously evaluates investment strategies by:
- **Point-in-time decisions**: Uses only data available at each decision date (no look-ahead bias)
- **Realistic trading**: Includes transaction costs, slippage, and position size limits
- **Periodic rebalancing**: Tests quarterly/monthly rebalancing based on screening criteria
- **Comprehensive metrics**: Tracks return, risk, and benchmark-relative performance

## Quick Start

### 1. Run a Simple Test

```bash
# From project root
uv run python models/backtesting/run_backtest.py models/backtesting/configs/test_backtest.yaml
```

### 2. View Results

The backtest will output:
- Performance summary (return, Sharpe ratio, max drawdown)
- Trade statistics (number of trades, win rate)
- Benchmark comparison (alpha, beta, information ratio)
- CSV files with detailed results

### 3. Customize Your Test

Edit configuration files in `models/backtesting/configs/` or create your own:

```yaml
# Example: configs/my_backtest.yaml
name: my_strategy_test
start_date: '2020-01-01'
end_date: '2023-12-31'
initial_capital: 100000
rebalance_frequency: quarterly

universe:
  - AAPL
  - MSFT
  - GOOGL
  # ... add your stocks/ETFs

strategy:
  quality_weight: 0.35
  value_weight: 0.35
  growth_weight: 0.20
  risk_weight: 0.10
  min_score: 0.50
```

## Directory Structure

```
models/backtesting/
├── core/
│   ├── engine.py       # Main backtesting engine
│   ├── portfolio.py    # Portfolio management with realistic trading
│   └── metrics.py      # Performance calculations
├── strategies/
│   └── screening.py    # Quality/Value/Growth/Risk screening strategy
├── data/
│   └── historical.py   # Point-in-time data fetcher (no look-ahead)
├── configs/
│   ├── test_backtest.yaml      # Simple test configuration
│   └── sp500_backtest.yaml     # Larger S&P 500 universe test
├── reports/            # Generated CSV and HTML reports
└── run_backtest.py    # Main runner script
```

## Configuration Options

### Basic Settings
- `start_date` / `end_date`: Backtest period
- `initial_capital`: Starting portfolio value
- `rebalance_frequency`: 'monthly', 'quarterly', or 'annually'
- `universe`: List of tickers to screen from

### Portfolio Constraints
- `max_positions`: Maximum number of stocks to hold
- `min_position_size`: Minimum allocation per stock (e.g., 0.02 = 2%)
- `max_position_size`: Maximum allocation per stock (e.g., 0.20 = 20%)

### Trading Costs
- `transaction_cost`: Cost per trade as percentage (e.g., 0.001 = 0.1%)
- `slippage`: Market impact as percentage (e.g., 0.001 = 0.1%)

### Strategy Parameters
- `quality_weight`: Weight for quality score (ROE, margins, debt ratios)
- `value_weight`: Weight for value score (P/E, P/B, dividend yield)
- `growth_weight`: Weight for growth score (revenue/earnings growth, momentum)
- `risk_weight`: Weight for risk score (beta, volatility, debt levels)
- `min_score`: Minimum composite score to include stock (0-1 scale)

## How It Works

### 1. Point-in-Time Analysis
At each rebalancing date, the system:
1. Fetches only historical data available at that date
2. Calculates quality, value, growth, and risk scores for each stock
3. Ranks stocks by composite score
4. Selects top-scoring stocks for the portfolio

### 2. Portfolio Construction
- Allocates capital based on stock scores (higher score = higher weight)
- Applies position size limits (min/max percentages)
- Maintains cash buffer (typically 5%) for flexibility

### 3. Realistic Trading
- Calculates exact shares to buy/sell for rebalancing
- Applies transaction costs and slippage to each trade
- Tracks trade history and portfolio turnover

### 4. Performance Measurement
- Calculates comprehensive metrics vs time and benchmarks
- Handles corporate actions and data gaps gracefully
- Provides rolling performance analysis

## Performance Metrics

### Returns
- **Total Return**: Cumulative return over backtest period
- **CAGR**: Compound Annual Growth Rate
- **Best/Worst Month**: Peak performance periods

### Risk Measures
- **Sharpe Ratio**: Risk-adjusted return (assumes 2% risk-free rate)
- **Sortino Ratio**: Return vs downside volatility
- **Maximum Drawdown**: Largest peak-to-trough decline
- **Volatility**: Annualized standard deviation of returns

### Trading Statistics
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Ratio of gains to losses
- **Portfolio Turnover**: How frequently positions change

### Benchmark Comparison (when benchmark specified)
- **Alpha**: Excess return vs benchmark
- **Beta**: Correlation with benchmark movements
- **Information Ratio**: Alpha divided by tracking error

## Example Results

```
BACKTEST RESULTS
============================================================

Period: 2020-01-01 to 2023-12-31
Initial Capital: $100,000.00
Final Value: $156,420.00

Performance Metrics:
  Total Return: 56.42%
  Annualized Return: 14.85%
  Sharpe Ratio: 1.12
  Max Drawdown: -18.3%
  Win Rate: 62.5%

Trading Activity:
  Number of Trades: 48
  Portfolio Turnover: 1.25

Benchmark Comparison (SPY):
  Benchmark Return: 43.2%
  Alpha: 13.2%
  Beta: 0.89
  Information Ratio: 0.74
```

## Common Use Cases

### 1. Strategy Validation
Test if your screening criteria would have generated alpha historically:
```bash
# Test your screening weights
uv run python models/backtesting/run_backtest.py configs/sp500_backtest.yaml
```

### 2. Parameter Optimization
Compare different weight combinations:
- High quality focus: quality=0.5, value=0.3, growth=0.2
- Balanced approach: quality=0.35, value=0.35, growth=0.3
- Growth focus: growth=0.4, quality=0.3, value=0.3

### 3. Universe Testing
Test on different stock universes:
- Large cap: S&P 500 components
- All cap: Russell 3000 components  
- International: Add European/Asian stocks
- Sector-specific: Technology, healthcare, etc.

### 4. Frequency Analysis
Compare rebalancing frequencies:
- Monthly: Higher turnover, more responsive
- Quarterly: Balanced approach
- Annual: Lower costs, tax efficient

## Limitations & Considerations

### Data Quality
- Relies on Yahoo Finance data (free but may have gaps)
- Corporate actions (splits, dividends) handled by yfinance
- Survivorship bias: Only includes stocks that existed during backtest period

### Look-Ahead Bias Prevention
- Uses only data available at each decision date
- Account for typical reporting delays (earnings released ~45 days after quarter)
- No use of future information in scoring

### Transaction Costs
- Includes basic bid-ask spread and commission estimates
- May not reflect institutional trading costs or market impact
- Assumes perfect execution (no failed trades)

### Market Regime
- Backtests reflect specific historical periods
- Strategy performance may vary in different market conditions
- Consider testing across multiple time periods and market cycles

## Advanced Usage

### Custom Strategies
Extend the framework with your own strategies:

```python
# Create custom strategy
class MyCustomStrategy(ScreeningStrategy):
    def generate_signals(self, market_data, current_portfolio, date):
        # Your custom logic here
        return target_weights

# Use in backtest  
strategy = MyCustomStrategy(config)
results = backtester.run(strategy)
```

### Batch Testing
Test multiple configurations:

```python
import glob
for config_file in glob.glob("models/backtesting/configs/*.yaml"):
    results = run_backtest(config_file)
    print(f"{config_file}: {results.get_summary()}")
```

### Integration with Main System
Use the same screening logic as your main analysis:

```python
from invest.analysis.pipeline import AnalysisPipeline
from invest.config.loader import load_analysis_config

# Use existing screening configuration
main_config = load_analysis_config("dashboard/configs/sp500_top100.yaml") 
# Adapt for backtesting...
```

## Troubleshooting

### Common Issues

1. **Data Download Errors**: Yahoo Finance may be temporarily unavailable
   - Solution: Retry after a few minutes or use cached data

2. **Memory Issues**: Large universes (500+ stocks) may use significant RAM
   - Solution: Reduce universe size or increase system memory

3. **Slow Performance**: Downloading data for many stocks takes time
   - Solution: Use smaller date ranges or fewer stocks for testing

4. **Missing Dependencies**: Import errors
   - Solution: Ensure dependencies are installed: `uv sync`

### Getting Help

- Check logs for detailed error messages
- Verify YAML configuration syntax
- Test with smaller universes first
- Review the example configurations in `models/backtesting/configs/`

---

*This backtesting framework helps you answer: "How would my investment strategy have performed historically?" with rigorous, unbiased testing.*
