# Enhanced DCF with Dividend Policy (Retired)

!!! warning "Retired Model"
    Enhanced DCF has been removed from the dashboard as of March 2026. This page is kept for reference. See [active models](index.md).

DCF model that explicitly accounts for dividend policy and payout ratios in cash flow projections.

## Overview

Enhanced DCF extends the basic DCF model by incorporating dividend policy into the valuation framework, recognizing that companies with different payout ratios should be valued differently.

## Key Differences from Standard DCF

- **Dividend Adjustment**: Accounts for cash returned to shareholders vs reinvested
- **Payout Ratio**: Explicitly models dividend vs retention decisions
- **Growth Impact**: Links retention rate to sustainable growth
- **Same Coverage**: ~98% of stocks (same as standard DCF)

## How It Works

Adjusts free cash flow based on:
```
Adjusted FCF = FCF × (1 - Payout_Ratio × Dividend_Tax_Rate)
```

Then applies standard DCF methodology with dividend-adjusted cash flows.

## When to Use

- Companies with significant dividend yields (>2%)
- Mature businesses with stable payout policies
- Cross-border investments (dividend tax considerations)
- Comparison with dividend discount model (DDM)

## See Also

- [DCF Model](dcf.md) - Standard version
- [Growth DCF](growth-dcf.md) - Alternative growth adjustment
- [RIM](rim.md) - Book value based alternative
