# Discounted Cash Flow (DCF) Model

The classic DCF model estimates intrinsic value by discounting projected future free cash flows to present value.

## Overview

DCF is the foundational valuation method taught in finance courses and used widely in investment banking. It's based on the principle that a company is worth the present value of all its future cash flows.

## How It Works

### 1. Free Cash Flow Calculation

```
FCF = Operating Cash Flow - Capital Expenditures
```

For each company, we calculate:
- Historical FCF trend
- FCF margin (FCF / Revenue)
- FCF growth rate

### 2. Projection Phase

**Growth Rate Estimation:**
- Use historical revenue growth if available
- Cap at reasonable limits (typically -50% to 200%)
- Apply sector-specific adjustments

**Projection Period:**
- Typically 5-10 years of explicit forecasts
- Year-by-year cash flow projections

### 3. Terminal Value

Two methods for perpetual value beyond projection period:

**Gordon Growth Model:**
```
Terminal Value = FCF_final × (1 + g) / (WACC - g)
```

Where:
- `g` = perpetual growth rate (typically 2-3%)
- `WACC` = Weighted Average Cost of Capital

### 4. Discount to Present Value

```
PV = Σ(FCF_t / (1 + WACC)^t) + (Terminal_Value / (1 + WACC)^n)
```

### 5. Per-Share Value

```
Fair Value per Share = Enterprise Value / Shares Outstanding
```

## Cost of Capital (WACC)

```
WACC = (E/V × Cost_of_Equity) + (D/V × Cost_of_Debt × (1 - Tax_Rate))
```

**Components:**
- **Cost of Equity**: CAPM model using beta, risk-free rate, market risk premium
- **Cost of Debt**: Interest expense / Total debt
- **Weights**: Market value proportions of equity and debt

## When DCF Works Best

### Ideal Candidates
- **Stable, predictable cash flows**: Mature companies with consistent FCF
- **Capital-light businesses**: High FCF conversion
- **Low cyclicality**: Predictable revenue streams
- **Examples**: Consumer staples, utilities, established tech

### Poor Candidates
- **Negative or volatile FCF**: Startups, turnarounds
- **High capital intensity**: Airlines, manufacturing
- **Financial institutions**: Banks, insurance (use RIM instead)
- **Commodity businesses**: Oil & gas, mining (highly cyclical)

## Limitations

1. **Sensitivity to Assumptions**: Small changes in growth rate or WACC dramatically affect value
2. **Terminal Value Dominance**: Often 60-80% of value comes from terminal value
3. **Forecast Uncertainty**: Projecting 5-10 years ahead is inherently uncertain
4. **Ignores Strategic Value**: M&A premiums, synergies not captured
5. **Working Capital**: Simplifies working capital dynamics

## Model Parameters

### Growth Rate Caps
- **Minimum**: -50% (deep contraction scenarios)
- **Maximum**: 200% (high-growth companies)
- **Typical**: 3-15% for mature companies

### WACC Bounds
- **Minimum**: 5% (ultra-safe businesses)
- **Maximum**: 20% (high-risk ventures)
- **Typical**: 8-12% for most companies

### Terminal Growth
- **Standard**: 2-3% (GDP growth proxy)
- **Mature Markets**: 1-2%
- **Emerging Markets**: 3-5%

## Implementation Example

```python
from invest.valuation.dcf_model import DCFModel

# Initialize model
dcf = DCFModel()

# Get valuation
result = dcf.calculate_fair_value(stock_data)

if result['suitable']:
    print(f"Fair Value: ${result['fair_value']:.2f}")
    print(f"Current Price: ${result['current_price']:.2f}")
    print(f"Margin of Safety: {result['margin_of_safety']:.1%}")
```

## Academic Foundation

### Core Papers
- **Modigliani & Miller (1958)**: "The Cost of Capital, Corporation Finance and the Theory of Investment"
  - Foundational work on capital structure and cost of capital

- **Gordon & Shapiro (1956)**: "Capital Equipment Analysis: The Required Rate of Profit"
  - Gordon Growth Model for terminal value

- **Damodaran (2012)**: "Investment Valuation"
  - Comprehensive DCF framework and implementation

### Empirical Evidence
- DCF valuations correlate 0.6-0.7 with subsequent returns (Francis et al., 2000)
- Works better for large-cap than small-cap stocks
- Accuracy improves with analyst forecast consensus vs historical trends

## Relationship to Other Models

- **Enhanced DCF**: Adds dividend policy considerations
- **Growth DCF**: Separates growth and maintenance CapEx
- **Multi-Stage DCF**: Multiple growth phases
- **RIM**: Alternative using book value and residual income
- **GBM Models**: ML-based ranking vs DCF's absolute valuation

## References

- Damodaran, A. (2012). *Investment Valuation: Tools and Techniques*. Wiley.
- Francis, J., Olsson, P., & Oswald, D. (2000). "Comparing the Accuracy and Explainability of Dividend, Free Cash Flow, and Abnormal Earnings Equity Value Estimates". *Journal of Accounting Research*.
- Gordon, M. J., & Shapiro, E. (1956). "Capital Equipment Analysis: The Required Rate of Profit". *Management Science*.
- Modigliani, F., & Miller, M. H. (1958). "The Cost of Capital, Corporation Finance and the Theory of Investment". *American Economic Review*.
