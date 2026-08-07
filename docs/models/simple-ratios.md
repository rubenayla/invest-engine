# Simple Ratios (Multiples) Model (Retired)

!!! warning "Retired Model"
    Simple Ratios has been removed from the dashboard as of March 2026 (broken implementation). This page is kept for reference. See [active models](index.md).

Quick valuation using market multiples - the fastest and most widely used method for ballpark estimates.

## Overview

The multiples approach values companies by comparing them to similar companies or industry averages using simple ratios. It's the go-to method for quick assessments and sanity checks.

## Core Multiples

### 1. Price-to-Earnings (P/E)

**Formula:**
```
Fair Value = Earnings × Industry_PE_Ratio
```

**Best For:**
- Mature, profitable companies
- Stable earnings
- Cross-industry comparisons

**Limitations:**
- Useless for unprofitable companies
- Distorted by one-time items
- Accounting policy differences

### 2. Price-to-Book (P/B)

**Formula:**
```
Fair Value = Book Value per Share × Industry_PB_Ratio
```

**Best For:**
- Asset-heavy businesses
- Financial institutions (banks, insurance)
- Distressed situations

**Limitations:**
- Ignores intangible assets
- Historical cost vs market value
- Less relevant for service/tech companies

### 3. Price-to-Sales (P/S)

**Formula:**
```
Fair Value = Revenue per Share × Industry_PS_Ratio
```

**Best For:**
- Unprofitable growth companies
- Early-stage businesses
- Revenue quality assessment

**Limitations:**
- Ignores profitability
- Margins vary widely
- Can justify overvaluations

### 4. EV/EBITDA

**Formula:**
```
Enterprise Value = EBITDA × Industry_EV/EBITDA_Ratio
```

**Best For:**
- Capital-intensive businesses
- Comparing across capital structures
- M&A valuations

**Limitations:**
- Ignores CapEx requirements
- EBITDA isn't cash flow
- Adjustments for non-recurring items

## How It Works

### 1. Industry Benchmark Selection

**Sector Averages:**
- Technology: High P/E (20-30x), high P/S (5-10x)
- Utilities: Low P/E (12-18x), high dividend yield
- Financial: Low P/B (0.8-1.5x), moderate P/E
- Consumer Staples: Moderate P/E (15-25x), stable margins

### 2. Peer Comparison

Choose comparable companies by:
- Same industry/sector
- Similar size (market cap)
- Similar growth profile
- Similar profitability

### 3. Multiple Application

```python
# Example: P/E multiple
sector_median_pe = 20.0
company_eps = 5.00
fair_value = company_eps * sector_median_pe  # $100
```

### 4. Quality Adjustments

Adjust for:
- **Growth**: Higher growth → higher multiple
- **Profitability**: Higher margins → premium
- **Risk**: Higher debt → discount
- **Quality**: Better ROIC → premium

## Model Implementation

### Coverage
- **Success Rate**: ~99% (almost always has at least one ratio)
- **Data Required**: Current financials only
- **Speed**: Fastest valuation method

### Averaging Strategy

Use median of available ratios:
```
ratios = [pe_value, pb_value, ps_value, ev_ebitda_value]
fair_value = median([r for r in ratios if r is not None])
```

## When Simple Ratios Work Best

### Ideal Use Cases
- **Quick screening**: Initial pass on hundreds of stocks
- **Sanity check**: Validate DCF/other models
- **Relative value**: "Cheaper than peers?"
- **Market sentiment**: How market prices sector

### Complementary Use
- Use with DCF for different perspectives
- Cross-validate with GBM rankings
- Combine multiple ratios for robustness

## Limitations

### 1. Backward-Looking
Ratios use historical earnings/book value, not future expectations

### 2. Ignores Growth
Standard multiples don't account for growth rates (use PEG ratio as adjustment)

### 3. Accounting Differences
GAAP vs IFRS, conservative vs aggressive policies

### 4. Cyclical Distortion
Peak earnings → low P/E → looks cheap but isn't
Trough earnings → high P/E → looks expensive but isn't

### 5. No Absolute Anchor
Entire market can be overvalued/undervalued

## Advanced Adjustments

### PEG Ratio
```
PEG = P/E / Growth_Rate
PEG < 1.0 = Potentially undervalued for growth
PEG > 2.0 = Potentially overvalued for growth
```

### Normalized Earnings
Use average earnings over cycle instead of current year

### Forward Multiples
Use next year's estimates instead of trailing

## Sector-Specific Guidelines

| Sector | Primary Multiple | Typical Range | Notes |
|--------|-----------------|---------------|--------|
| Technology | P/S, P/E | 5-15x Sales | High growth, often unprofitable early |
| Financial | P/B, P/E | 0.8-1.5x Book | Book value is meaningful |
| Healthcare | P/E, EV/EBITDA | 15-25x Earnings | R&D heavy, binary outcomes |
| Utilities | Dividend Yield, P/E | 3-5% Yield | Stable, regulated |
| Consumer Staples | P/E, EV/EBITDA | 18-25x Earnings | Stable, branded |
| Energy | EV/EBITDA, P/CF | 5-8x EBITDA | Cyclical, commodity-driven |
| Industrials | P/E, EV/EBITDA | 12-20x Earnings | Capital intensive |
| Real Estate | P/FFO, Dividend Yield | 12-18x FFO | Use FFO not earnings |

## Implementation Example

```python
from invest.valuation.ratios_model import SimpleRatiosModel

# Initialize
ratios_model = SimpleRatiosModel()

# Calculate
result = ratios_model.calculate_fair_value(stock_data)

print(f"P/E Valuation: ${result['details']['pe_value']:.2f}")
print(f"P/B Valuation: ${result['details']['pb_value']:.2f}")
print(f"Consensus (Median): ${result['fair_value']:.2f}")
```

## Combining with Other Models

**Triangulation Approach:**
1. Simple Ratios: Quick market-based view ($100)
2. DCF: Intrinsic cash flow value ($120)
3. GBM Ranking: Relative attractiveness (Top 20%)

If all agree → High confidence
If diverge → Investigate assumptions

## Academic Foundation

### Core Research
- **Graham & Dodd (1934)**: "Security Analysis"
  - Foundational work on value investing and multiples

- **Damodaran (2002)**: "Investment Valuation"
  - Comprehensive treatment of relative valuation

- **Liu, Nissim & Thomas (2002)**: "Equity Valuation Using Multiples"
  - Empirical comparison of which multiples work best

### Key Findings
- **Best Predictor**: Forward P/E > Trailing P/E > P/B > P/S
- **Industry Matters**: Multiples vary 3-5x across sectors
- **Earnings Quality**: Accruals-adjusted earnings improve accuracy
- **Combination**: Using multiple ratios beats single metric

## When to Use

### Primary Valuation
- Initial screening of large universes
- Quick comparative analysis
- Market-relative opportunities

### Secondary Check
- Validate DCF assumptions
- Reality check on growth expectations
- Peer comparison

### Avoid As Primary
- High-growth unprofitable companies
- Turnaround situations
- Unique business models with no peers

## References

- Damodaran, A. (2002). *Investment Valuation: Tools and Techniques*. Wiley.
- Graham, B., & Dodd, D. (1934). *Security Analysis*. McGraw-Hill.
- Liu, J., Nissim, D., & Thomas, J. (2002). "Equity Valuation Using Multiples". *Journal of Accounting Research*.
- Penman, S. (1998). "A Synthesis of Equity Valuation Techniques and the Terminal Value Calculation for the Dividend Discount Model". *Review of Accounting Studies*.
