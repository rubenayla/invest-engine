# Residual Income Model (RIM)

Valuation based on book value plus the present value of expected "excess" returns above the cost of equity.

## Overview

RIM is particularly well-suited for financial institutions and asset-heavy businesses where book value is meaningful. It focuses on returns above what shareholders require, making it complementary to DCF.

## Core Concept

**Key Insight:** A company is worth its book value plus (or minus) the present value of all future returns above (or below) the cost of equity.

```
Value = Book Value + PV(Future Residual Income)
```

Where:
```
Residual Income = (ROE - Cost of Equity) × Book Value
```

## How It Works

### 1. Starting Point: Book Value

```
Book Value per Share = Total Equity / Shares Outstanding
```

**Quality Check:**
- Adjust for intangibles (goodwill)
- Check for off-balance sheet items
- Verify accounting quality

### 2. Calculate Residual Income

**For Each Future Period:**
```
RI_t = (ROE_t - r_e) × BV_{t-1}
```

Where:
- `ROE_t` = Return on Equity in period t
- `r_e` = Cost of Equity (required return)
- `BV_{t-1}` = Book Value at start of period

### 3. Project Book Value Growth

```
BV_t = BV_{t-1} × (1 + g)
```

Where `g` = Sustainable growth rate = ROE × (1 - Payout Ratio)

### 4. Terminal Value

**Perpetuity Method:**
```
Terminal RI = RI_final / (r_e - g_terminal)
```

**Fade-to-Normal Method:**
```
Assume ROE gradually converges to cost of equity
```

### 5. Sum to Fair Value

```
Fair Value = BV_0 + Σ(RI_t / (1 + r_e)^t) + (Terminal_RI / (1 + r_e)^n)
```

## When RIM Works Best

### Ideal Candidates

**Financial Institutions:**
- Banks
- Insurance companies
- Asset managers
- REITs (with adjustments)

**Characteristics:**
- Meaningful book value
- Stable ROE
- Transparent balance sheets
- Regulated industries

### Why It's Better Than DCF for Banks

1. **Cash Flow Ambiguity**: Bank "cash flows" are hard to define
2. **Book Value Relevance**: Regulatory capital is key metric
3. **ROE Focus**: Banks managed on ROE targets
4. **Balance Sheet Business**: Assets/liabilities are the product

## Model Advantages

### 1. Less Terminal Value Dependence
Unlike DCF where terminal value is 60-80%, RIM starts with current book value (tangible anchor)

### 2. Accounting-Based
Uses reported financials directly, easier to verify

### 3. Mean Reversion
Natural assumption that excess returns fade over time (competitive forces)

### 4. Handles Negatives
Works even with negative earnings (as long as positive equity)

## Implementation

### Parameters

**Cost of Equity (CAPM):**
```
r_e = Risk_Free_Rate + Beta × Market_Risk_Premium
```

**Typical Values:**
- Banks: 10-12%
- Utilities: 8-10%
- Industrial: 10-14%

**ROE Assumptions:**
- Use historical average
- Adjust for one-time items
- Consider industry trends

**Forecast Horizon:**
- Explicit forecasts: 5-10 years
- Fade period: 5 years to terminal
- Terminal ROE: Converge to cost of equity

### Code Example

```python
from invest.valuation.rim_model import RIMModel

# Initialize
rim = RIMModel()

# Calculate
result = rim.calculate_fair_value(stock_data)

if result['suitable']:
    print(f"Book Value: ${result['details']['book_value']:.2f}")
    print(f"Residual Income PV: ${result['details']['ri_pv']:.2f}")
    print(f"Fair Value: ${result['fair_value']:.2f}")
```

## Key Assumptions

### 1. Clean Surplus Relation

```
BV_t = BV_{t-1} + Earnings_t - Dividends_t
```

Must hold for RIM to be theoretically sound. Violated by:
- Stock buybacks (adjust for repurchases)
- Currency translation adjustments
- Pension accounting

### 2. ROE Mean Reversion

**Empirical Evidence:**
- High ROE (>20%) typically fades 50% in 5 years
- Low ROE (<10%) typically improves but slowly
- Industry median is attractor

**Competitive Forces:**
- High returns attract competition
- Low returns force restructuring or exit

### 3. Book Value Quality

**Red Flags:**
- Large goodwill (>30% of equity)
- Frequent write-downs
- Off-balance sheet vehicles
- Mark-to-model assets

## Sector Applications

### Banks
**Perfect fit:**
- Book value = regulatory capital
- ROE = primary management metric
- Stable business model

**Adjustments:**
- Normalize for credit cycles
- Adjust for loan loss reserves
- Consider Basel III impacts

### Insurance
**Good fit:**
- Assets = liabilities + equity
- Underwriting profit + investment returns

**Adjustments:**
- Normalize catastrophe losses
- Adjust reserves for conservatism
- Consider float value

### Asset-Heavy Industrials
**Moderate fit:**
- Book value less relevant
- ROIC often better than ROE

**Use with caution:**
- Depreciation policy affects book value
- Asset impairments common
- Intangibles growing

## Limitations

### 1. Growth Companies
Book value is tiny relative to intangible value (brand, patents, network effects)

### 2. Accounting Dependence
Vulnerable to accounting manipulation:
- Aggressive revenue recognition
- Understated reserves
- Goodwill avoidance

### 3. Assumes Clean Surplus
Share buybacks, special dividends, FX adjustments violate assumption

### 4. Terminal Value Still Matters
If ROE >> r_e persists, terminal value dominates (same DCF problem)

## Comparison to DCF

| Aspect | RIM | DCF |
|--------|-----|-----|
| Starting Point | Book Value | Cash Flows |
| Best For | Banks, asset-heavy | Operating companies |
| Terminal Value | Smaller component | Larger component |
| Accounting | Direct use | Adjustments needed |
| Growth Bias | Less sensitive | Very sensitive |
| Intangibles | Undervalues | Better capture |

## Academic Foundation

### Core Theory
- **Edwards & Bell (1961)**: *The Theory and Measurement of Business Income*
  - Early residual income concepts

- **Ohlson (1995)**: "Earnings, Book Values, and Dividends in Equity Valuation"
  - Modern RIM framework
  - Proof of equivalence to dividend discount model

- **Feltham & Ohlson (1995)**: "Valuation and Clean Surplus Accounting"
  - Clean surplus relation formalization

### Empirical Validation
- **Frankel & Lee (1998)**: RIM explains 70% of stock price variation
- **Dechow, Hutton & Sloan (1999)**: RIM outperforms DCF for banks
- **Penman & Sougiannis (1998)**: Combining earnings and book value improves forecasts

## Advanced Extensions

### 1. ROE Decomposition (DuPont)
```
ROE = Net Margin × Asset Turnover × Equity Multiplier
```

Forecast each component separately for detailed analysis

### 2. Economic Value Added (EVA)
Related concept: Value = Capital + PV(EVA)
```
EVA = NOPAT - (Capital × WACC)
```

### 3. ROIC-Based Variant
Use ROIC instead of ROE for capital structure neutrality

## When to Use

### Primary Valuation Method
- Banks and financial institutions
- Mature, stable companies with clean accounting
- Asset-heavy businesses with transparent books

### Secondary Check
- Validate DCF for companies with significant book value
- Assess quality of returns (ROE vs cost of equity)

### Avoid
- Tech/software companies (minimal book value)
- Companies with aggressive accounting
- High-growth unprofitable companies

## References

- Dechow, P., Hutton, A., & Sloan, R. (1999). "An Empirical Assessment of the Residual Income Valuation Model". *Journal of Accounting and Economics*.
- Edwards, E., & Bell, P. (1961). *The Theory and Measurement of Business Income*. University of California Press.
- Feltham, G., & Ohlson, J. (1995). "Valuation and Clean Surplus Accounting for Operating and Financial Activities". *Contemporary Accounting Research*.
- Frankel, R., & Lee, C. (1998). "Accounting Valuation, Market Expectation, and Cross-Sectional Stock Returns". *Journal of Accounting and Economics*.
- Ohlson, J. (1995). "Earnings, Book Values, and Dividends in Equity Valuation". *Contemporary Accounting Research*.
- Penman, S., & Sougiannis, T. (1998). "A Comparison of Dividend, Cash Flow, and Earnings Approaches to Equity Valuation". *Contemporary Accounting Research*.
