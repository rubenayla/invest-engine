# Configuration Options

Comprehensive reference for all configuration parameters in the Systematic Investment Analysis Framework.

## Configuration File Structure

All configurations use YAML format with these main sections:

```yaml
name: "configuration_name"
description: "Configuration description"

universe:          # Stock selection criteria
quality:          # Financial strength parameters
value:            # Valuation criteria  
growth:           # Growth requirements
risk:             # Risk assessment parameters
valuation:        # Valuation model settings
max_results: 50   # Output limits
sort_by: "composite_score"  # Ranking criteria
```

## Universe Configuration

### Basic Parameters

```yaml
universe:
  region: "US"                    # Region selection
  min_market_cap: 1000           # Minimum market cap ($M)
  max_market_cap: 100000         # Maximum market cap ($M)
  
  # Stock list options
  custom_tickers: ["AAPL", "GOOGL"]        # Specific stocks
  pre_screening_universe: "sp500"          # Predefined lists
  top_n_by_market_cap: 100                # Top N by size
  
  # Sector filtering
  sectors: ["Technology", "Healthcare"]    # Include sectors
  exclude_sectors: ["Utilities"]          # Exclude sectors
```

### Region Options

| Region | Description | Coverage |
|--------|-------------|----------|
| `"US"` | United States | S&P 500, major exchanges |
| `"EU"` | Europe | Major European stocks |
| `"JP"` | Japan | Major Japanese stocks |
| `"ALL"` | Global | All available regions |

### Predefined Universes

| Universe | Stocks | Description |
|----------|--------|-------------|
| `"sp500"` | ~503 | S&P 500 constituents |
| `"sp100"` | ~100 | S&P 100 large caps |
| `"nasdaq100"` | ~100 | NASDAQ 100 tech focus |

### Sector Classifications

Available sectors for filtering:
- Technology
- Healthcare  
- Financial Services
- Consumer Cyclical
- Consumer Defensive
- Communication Services
- Industrials
- Energy
- Basic Materials
- Real Estate
- Utilities

## Quality Configuration

### Financial Strength Metrics

```yaml
quality:
  min_roic: 0.12                 # Return on Invested Capital
  min_roe: 0.15                  # Return on Equity
  min_current_ratio: 1.2         # Current assets / Current liabilities
  max_debt_equity: 0.6           # Total debt / Total equity
  min_interest_coverage: 5.0     # EBIT / Interest expense
```

### Parameter Ranges

| Parameter | Typical Range | Conservative | Aggressive |
|-----------|---------------|--------------|------------|
| `min_roic` | 0.08 - 0.20 | 0.15+ | 0.08+ |
| `min_roe` | 0.10 - 0.25 | 0.18+ | 0.10+ |
| `min_current_ratio` | 1.0 - 2.0 | 1.5+ | 1.0+ |
| `max_debt_equity` | 0.3 - 1.0 | 0.4 | 0.8 |
| `min_interest_coverage` | 2.0 - 10.0 | 5.0+ | 2.0+ |

### Sector Adjustments

Different sectors have different normal ranges:

#### Technology Sector
```yaml
quality:
  min_roic: 0.15    # Higher due to asset-light models
  min_roe: 0.18     # Expect higher returns
  max_debt_equity: 0.3  # Typically low debt
```

#### Utilities Sector
```yaml
quality:
  min_roic: 0.06    # Lower due to capital intensity
  min_roe: 0.10     # Regulated returns
  max_debt_equity: 1.2  # Infrastructure requires debt
```

## Value Configuration

### Valuation Metrics

```yaml
value:
  max_pe: 25                     # Price / Earnings
  max_pb: 3.5                    # Price / Book
  max_ev_ebitda: 15              # Enterprise Value / EBITDA
  max_ev_ebit: 20                # Enterprise Value / EBIT
  max_p_fcf: 30                  # Price / Free Cash Flow
  min_dividend_yield: 0.02       # Minimum dividend yield
```

### Sector-Specific Valuations

#### High Growth Sectors (Technology)
```yaml
value:
  max_pe: 35        # Accept higher multiples
  max_pb: 8.0       # Growth premium
  max_ev_ebitda: 25 # SaaS/platform businesses
```

#### Stable Sectors (Utilities/Consumer Staples)
```yaml
value:
  max_pe: 20        # Lower multiples expected
  max_pb: 2.5       # Asset-based valuation
  max_ev_ebitda: 12 # Stable cash flows
```

#### Cyclical Sectors (Energy/Materials)
```yaml
value:
  max_pe: 15        # Use normalized earnings
  max_pb: 1.5       # Book value important
  max_ev_ebitda: 8  # Cycle-adjusted multiples
```

## Growth Configuration

### Growth Metrics

```yaml
growth:
  min_revenue_growth: 0.05       # Revenue growth rate
  min_earnings_growth: 0.08      # Earnings growth rate
  min_fcf_growth: 0.03           # Free cash flow growth
  min_book_value_growth: 0.04    # Book value growth
  
  # Advanced options
  revenue_consistency: 0.8       # Growth consistency requirement
  earnings_quality: 0.7          # Earnings quality threshold
```

### Growth Expectations by Sector

#### High Growth Sectors
```yaml
growth:
  min_revenue_growth: 0.15   # 15%+ revenue growth
  min_earnings_growth: 0.20  # 20%+ earnings growth
  # Technology, Biotech, High-growth consumer
```

#### Stable Growth Sectors  
```yaml
growth:
  min_revenue_growth: 0.03   # 3%+ revenue growth
  min_earnings_growth: 0.05  # 5%+ earnings growth
  # Utilities, Consumer staples, REITs
```

#### Cyclical Sectors
```yaml
growth:
  min_revenue_growth: -0.05  # Allow cyclical declines
  min_earnings_growth: -0.10 # Volatile earnings acceptable
  # Energy, Materials, Industrials
```

## Risk Configuration

### Risk Assessment Parameters

```yaml
risk:
  max_beta: 1.5                  # Market risk (volatility)
  min_liquidity_ratio: 1.0       # Liquidity requirements
  max_concentration_risk: 0.3    # Customer/geographic concentration
  cyclical_adjustment: true      # Apply sector adjustments
  
  # Advanced risk metrics
  max_financial_leverage: 3.0    # Financial risk
  min_altman_z_score: 2.5       # Bankruptcy risk
```

### Risk Tolerance Levels

#### Conservative Risk Profile
```yaml
risk:
  max_beta: 1.0             # Low volatility
  min_liquidity_ratio: 1.5  # Strong liquidity
  max_concentration_risk: 0.2  # Diversified revenue
  cyclical_adjustment: true    # Sector-aware
```

#### Moderate Risk Profile
```yaml
risk:
  max_beta: 1.3             # Moderate volatility
  min_liquidity_ratio: 1.2  # Adequate liquidity  
  max_concentration_risk: 0.3  # Some concentration OK
  cyclical_adjustment: true    # Sector-aware
```

#### Aggressive Risk Profile
```yaml
risk:
  max_beta: 2.0             # High volatility acceptable
  min_liquidity_ratio: 1.0  # Basic liquidity only
  max_concentration_risk: 0.5  # Higher concentration OK
  cyclical_adjustment: false   # Raw metrics
```

## Valuation Configuration

### Model Selection

```yaml
valuation:
  models: ["dcf", "rim"]         # Valuation models to run
  scenarios: ["bear", "base", "bull"]  # Scenario analysis
  
  # DCF Model parameters
  dcf_years: 10                  # Projection years
  terminal_growth_rate: 0.025    # Terminal growth (2.5%)
  risk_free_rate: 0.04          # Override risk-free rate
  market_risk_premium: 0.06     # Equity risk premium
  
  # RIM Model parameters
  rim_years: 10                  # Projection years
  required_return: 0.10         # Required return rate
  fade_period: 5                # ROE fade to industry average
```

### Scenario Parameters

#### Conservative (Bear) Scenario
```yaml
valuation:
  terminal_growth_rate: 0.02    # 2% terminal growth
  market_risk_premium: 0.08     # Higher risk premium
  growth_rate_adjustment: 0.5   # 50% of projected growth
```

#### Base Scenario
```yaml
valuation:
  terminal_growth_rate: 0.025   # 2.5% terminal growth
  market_risk_premium: 0.06     # Standard risk premium
  growth_rate_adjustment: 1.0   # Full projected growth
```

#### Optimistic (Bull) Scenario
```yaml
valuation:
  terminal_growth_rate: 0.03    # 3% terminal growth
  market_risk_premium: 0.05     # Lower risk premium
  growth_rate_adjustment: 1.2   # 120% of projected growth
```

## Output Configuration

### Results Control

```yaml
max_results: 50                  # Maximum stocks in output
sort_by: "composite_score"       # Primary sort criterion
generate_reports: true           # Generate detailed reports
save_data: true                 # Save intermediate calculations

# Additional output options
include_failed_stocks: true      # Include filtered-out stocks
detailed_scoring: true           # Show sub-component scores
sector_analysis: true           # Include sector benchmarking
```

### Sort Options

| Sort Criterion | Description |
|----------------|-------------|
| `"composite_score"` | Overall weighted score |
| `"quality_score"` | Financial strength ranking |
| `"value_score"` | Valuation attractiveness |
| `"growth_score"` | Growth prospects |
| `"market_cap"` | Company size |
| `"risk_score"` | Risk level (ascending) |

## Advanced Configuration

### Custom Scoring Weights

```yaml
scoring:
  quality_weight: 0.30          # 30% of composite score
  value_weight: 0.30            # 30% of composite score
  growth_weight: 0.25           # 25% of composite score
  risk_weight: 0.15             # 15% of composite score
```

### Filtering Thresholds

```yaml
filtering:
  min_quality_score: 40         # Minimum quality threshold
  min_value_score: 30           # Minimum value threshold
  min_growth_score: 20          # Minimum growth threshold
  max_risk_score: 80            # Maximum risk threshold
  min_composite_score: 50       # Minimum overall threshold
```

### Data Quality Controls

```yaml
data_quality:
  min_data_completeness: 0.8    # 80% of metrics must be available
  max_data_age_days: 90         # Maximum data staleness
  exclude_delisted: true        # Remove delisted stocks
  exclude_penny_stocks: true    # Remove stocks under $5
```

## Configuration Examples

### Conservative Value Strategy

```yaml
name: "conservative_value"
description: "High-quality companies at reasonable prices"

universe:
  pre_screening_universe: "sp500"
  min_market_cap: 5000          # Large caps only

quality:
  min_roic: 0.15                # Strong returns
  min_roe: 0.18
  max_debt_equity: 0.4          # Conservative debt

value:
  max_pe: 18                    # Reasonable multiples
  max_pb: 2.5
  max_ev_ebitda: 12

growth:
  min_revenue_growth: 0.03      # Steady growth
  min_earnings_growth: 0.05

risk:
  max_beta: 1.1                 # Lower volatility
  cyclical_adjustment: true

max_results: 25
```

### Aggressive Growth Strategy

```yaml
name: "aggressive_growth"
description: "High-growth companies with expansion potential"

universe:
  sectors: ["Technology", "Healthcare", "Consumer Cyclical"]
  min_market_cap: 1000

quality:
  min_roic: 0.12                # Good returns
  min_roe: 0.15
  max_debt_equity: 0.8          # Allow more leverage

value:
  max_pe: 40                    # Accept growth premiums
  max_pb: 8.0
  max_ev_ebitda: 25

growth:
  min_revenue_growth: 0.15      # Strong growth required
  min_earnings_growth: 0.20

risk:
  max_beta: 1.8                 # Accept volatility
  cyclical_adjustment: false

max_results: 30
```

## Configuration Validation

The framework validates all parameters and provides helpful error messages:

```yaml
# This will generate validation errors:
quality:
  min_roe: 15.0                 # ERROR: Should be 0.15 (decimal)
  max_debt_equity: -0.5         # ERROR: Cannot be negative
  
value:
  max_pe: 0                     # ERROR: Must be positive
```

## Best Practices

### Parameter Selection

1. **Start with sector benchmarks** - Research typical ranges for your target sectors
2. **Consider market conditions** - Adjust for bull/bear markets
3. **Backtest configurations** - Validate historical performance
4. **Document reasoning** - Note why each threshold was chosen

### Common Mistakes

❌ **Using percentage format** - Use 0.15 not 15 for 15%
❌ **Ignoring sector differences** - Tech vs utility expectations  
❌ **Over-optimization** - Fitting criteria to desired results
❌ **Static thresholds** - Not adjusting for market cycles

### Maintenance

- Review and update quarterly
- Adjust for changing market conditions
- Monitor results vs. expectations
- Consider sector rotation impacts

## Next Steps

- **[Running Analysis](running-analysis.md)** - Execute your configuration
- **[Understanding Results](understanding-results.md)** - Interpret the output
- **[Tutorials](../tutorials/custom-configurations.md)** - Step-by-step examples