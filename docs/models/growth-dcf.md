# Growth-Adjusted DCF (Retired)

!!! warning "Retired Model"
    Growth DCF has been removed from the dashboard as of March 2026 (85% failure rate). This page is kept for reference. See [active models](index.md).

DCF variant that separates growth CapEx from maintenance CapEx, solving traditional DCF's bias against reinvestment.

## Overview

Traditional DCF penalizes companies that reinvest heavily for growth by subtracting all CapEx from cash flow. Growth DCF recognizes that growth investments create future value and should be treated differently.

## Key Innovation

**CapEx Separation:**
```
Maintenance CapEx = Depreciation (sustains current operations)
Growth CapEx = Total CapEx - Maintenance CapEx (creates new capacity)
```

**Adjusted FCF:**
```
FCF_growth_adjusted = Operating Cash Flow - Maintenance CapEx
# Growth CapEx excluded, treated as investment not cost
```

## When to Use

### Ideal For
- High-growth companies (>15% revenue growth)
- Capital-intensive growth (manufacturing expansion, new facilities)
- Tech companies investing in R&D and infrastructure
- Retailers expanding store count

### Advantages Over Standard DCF
- **Fair to growth**: Doesn't penalize Amazon-style reinvestment
- **Better comps**: Growing vs mature companies more comparable
- **Realistic**: Separates value-creating vs value-maintaining spend

### Limitations
- **Estimation required**: Separating CapEx types is subjective
- **Lower coverage**: ~18% vs 98% for standard DCF
- **Data intensive**: Needs detailed CapEx breakdowns

## Implementation

Uses depreciation as proxy for maintenance CapEx when detailed breakdown unavailable.

## See Also

- [DCF Model](dcf.md) - Standard version
- [Multi-Stage DCF](multi-stage-dcf.md) - Different growth phases
- [Enhanced DCF](dcf-enhanced.md) - Dividend adjustments
