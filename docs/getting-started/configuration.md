# Configuration

Learn how to customize the analysis framework by creating and modifying configuration files.

## Configuration Structure

All analysis parameters are defined in YAML configuration files stored in the `dashboard/configs/` directory. Each configuration defines:

- **Stock universe** - Which stocks to analyze
- **Screening criteria** - Quality, value, growth, and risk thresholds
- **Valuation models** - DCF, RIM parameters
- **Output options** - Results format and limits

## Basic Configuration

Here's a simple configuration example:

```yaml
name: "my_analysis"
description: "Custom stock screening strategy"

universe:
  region: "US"
  min_market_cap: 1000  # $1B minimum

quality:
  min_roic: 0.12        # 12% minimum ROIC
  min_roe: 0.15         # 15% minimum ROE
  max_debt_equity: 0.6   # Maximum 60% debt/equity

value:
  max_pe: 25            # Maximum P/E ratio
  max_pb: 3.5           # Maximum P/B ratio

growth:
  min_revenue_growth: 0.03  # Minimum 3% revenue growth

risk:
  max_beta: 1.5         # Not too volatile

max_results: 50
sort_by: "composite_score"
```

## Configuration Sections

### Universe Selection

Define which stocks to analyze:

```yaml
universe:
  region: "US"                    # US, EU, JP, ALL
  min_market_cap: 1000           # $1B minimum (in millions)
  max_market_cap: 100000         # $100B maximum (optional)
  
  # Sector filters
  sectors: ["Technology", "Healthcare"]           # Include only these
  exclude_sectors: ["Real Estate", "Utilities"]  # Exclude these
  
  # Custom stock list
  custom_tickers: ["AAPL", "GOOGL", "MSFT"]
  
  # Predefined universes
  pre_screening_universe: "sp500"  # Use S&P 500 stocks
  top_n_by_market_cap: 100        # Top 100 by market cap
```

### Quality Criteria

Financial strength and stability metrics:

```yaml
quality:
  min_roic: 0.12                 # Return on Invested Capital
  min_roe: 0.15                  # Return on Equity  
  min_current_ratio: 1.2         # Current assets / Current liabilities
  max_debt_equity: 0.6           # Total debt / Total equity
  min_interest_coverage: 5.0     # EBIT / Interest expense
```

### Value Criteria

Valuation and price metrics:

```yaml
value:
  max_pe: 25                     # Price / Earnings ratio
  max_pb: 3.5                    # Price / Book ratio
  max_ev_ebitda: 15              # Enterprise Value / EBITDA
  max_ev_ebit: 20                # Enterprise Value / EBIT
  max_p_fcf: 30                  # Price / Free Cash Flow
```

### Growth Criteria

Business growth and expansion metrics:

```yaml
growth:
  min_revenue_growth: 0.03       # Minimum revenue growth rate
  min_earnings_growth: 0.05      # Minimum earnings growth rate
  min_fcf_growth: 0.02           # Minimum free cash flow growth
  min_book_value_growth: 0.03    # Minimum book value growth
```

### Risk Assessment

Risk and volatility parameters:

```yaml
risk:
  max_beta: 1.5                  # Maximum market risk (beta)
  min_liquidity_ratio: 1.0       # Minimum liquidity measures
  max_concentration_risk: 0.3    # Geographic/customer concentration
  cyclical_adjustment: true      # Apply sector-specific adjustments
```

### Valuation Models

Configure valuation model parameters:

```yaml
valuation:
  models: ["dcf", "rim"]         # Models to run
  scenarios: ["bear", "base", "bull"]  # Scenario analysis
  
  # DCF specific parameters
  dcf_years: 10                  # Projection period
  terminal_growth_rate: 0.025    # Terminal growth rate (2.5%)
  risk_free_rate: 0.04           # Override risk-free rate
  
  # RIM specific parameters
  rim_years: 10                  # Projection period
  required_return: 0.10          # Required return rate
```

### Output Options

Control results and formatting:

```yaml
max_results: 50                  # Maximum stocks in final results
sort_by: "composite_score"       # Sort criterion
generate_reports: true           # Generate detailed reports
save_data: true                  # Save intermediate data
```

## Pre-built Configurations

The framework includes several ready-to-use configurations:

### Conservative Value Strategy
```yaml
# dashboard/configs/conservative_value.yaml
quality:
  min_roic: 0.15      # High quality requirement
  min_roe: 0.18
  max_debt_equity: 0.4  # Low debt

value:
  max_pe: 20          # Reasonable valuation
  max_pb: 2.5
```

### Aggressive Growth Strategy
```yaml
# dashboard/configs/aggressive_growth.yaml
growth:
  min_revenue_growth: 0.15  # High growth requirement
  min_earnings_growth: 0.20

value:
  max_pe: 40          # Accept higher multiples
  max_pb: 8.0
```

### S&P 500 Full Analysis
```yaml
# dashboard/configs/sp500_full.yaml
universe:
  pre_screening_universe: "sp500"
  
max_results: 503      # Include all S&P 500 stocks
```

## Creating Custom Configurations

### 1. Copy Existing Configuration

Start with a similar strategy:
```bash
cp dashboard/configs/sp500_full.yaml dashboard/configs/my_strategy.yaml
```

### 2. Modify Parameters

Edit the YAML file to match your investment criteria:

```yaml
name: "my_dividend_strategy"
description: "Focus on dividend-paying quality companies"

quality:
  min_roe: 0.12
  max_debt_equity: 0.8

value:
  max_pe: 30
  
# Add dividend-specific criteria
custom_filters:
  min_dividend_yield: 0.02  # 2% minimum dividend yield
```

### 3. Test Configuration

```bash
uv run python scripts/systematic_analysis.py dashboard/configs/my_strategy.yaml --save-csv
```

## Advanced Configuration

### Sector-Specific Adjustments

```yaml
risk:
  cyclical_adjustment: true
  
# Automatic adjustments by sector:
# - Technology: Higher P/E acceptable, higher growth expected
# - Utilities: Lower growth acceptable, stable margins expected
# - Energy: Higher volatility acceptable, cyclical patterns considered
```

### Multiple Scenarios

```yaml
valuation:
  scenarios: ["bear", "base", "bull"]
  
# Generates valuations under different assumptions:
# - Bear: Conservative growth, higher discount rates
# - Base: Expected growth, market discount rates  
# - Bull: Optimistic growth, lower discount rates
```

## Configuration Validation

The framework validates all configurations and will show helpful error messages:

```bash
# Invalid configuration example
ERROR: quality.min_roe must be between 0.0 and 1.0, got 15.0
HINT: Use decimal format (0.15 for 15%)
```

## Best Practices

### Start Conservative
- Begin with stricter criteria
- Gradually relax constraints if needed
- Document your reasoning for each threshold

### Sector Considerations
- Technology: Higher P/E ratios acceptable (25-40)
- Utilities: Lower growth requirements (3-5%)
- Banks: Different debt metrics (use book value ratios)

### Backtesting
- Test configurations on historical data
- Verify results align with investment thesis
- Adjust based on performance analysis

## Example Workflows

### Value Investing Focus
```yaml
quality:
  min_roic: 0.12
  min_roe: 0.15
  max_debt_equity: 0.5

value:
  max_pe: 18
  max_pb: 2.0
  max_ev_ebitda: 12
```

### Growth Stock Screening
```yaml
growth:
  min_revenue_growth: 0.10
  min_earnings_growth: 0.15

value:
  max_pe: 45  # Accept higher multiples for growth
  max_pb: 8.0
```

### Dividend Aristocrats
```yaml
quality:
  min_roe: 0.10
  max_debt_equity: 0.8

# Focus on stability over growth
growth:
  min_revenue_growth: 0.00  # Accept flat growth
  
# Custom dividend requirements would be added here
```

## Next Steps

- [User Guide](../user-guide/overview.md) - Learn to run comprehensive analyses
- [Understanding Results](../user-guide/understanding-results.md) - Interpret screening output
- [Configuration Schema](../api-reference/configuration.md) - Complete parameter reference