# Multi-Stage DCF (Retired)

!!! warning "Retired Model"
    Multi-Stage DCF has been removed from the dashboard as of March 2026 (85% failure rate). This page is kept for reference. See [active models](index.md).

DCF model that uses different growth rates for different time periods, capturing realistic corporate lifecycle transitions.

## Overview

Multi-Stage DCF recognizes that companies don't grow at constant rates forever. Most businesses transition through phases: high growth → moderate growth → mature stable growth. This model explicitly models those transitions.

## Key Innovation

**Variable Growth Phases:**
```
Phase 1: High Growth (Years 1-5)     → 20% FCF growth
Phase 2: Transition (Years 6-10)     → 15% → 10% → 5%
Phase 3: Terminal/Perpetuity (Year 11+) → 3% stable growth
```

Instead of single-stage DCF's constant growth assumption, multi-stage allows growth to decline over time.

## Model Structure

### Three-Stage DCF (Most Common)

**Stage 1: Explicit High Growth (5-7 years)**
```
FCF_t = FCF_0 × (1 + g_high)^t
PV_Stage1 = Σ [FCF_t / (1 + WACC)^t]
```

**Stage 2: Transition Period (5-7 years)**
```
g_t = g_high - [(g_high - g_terminal) × (t - t1) / (t2 - t1)]
# Linear decline from high growth to terminal growth
```

**Stage 3: Terminal Value (Perpetuity)**
```
Terminal_Value = FCF_final × (1 + g_terminal) / (WACC - g_terminal)
PV_Terminal = Terminal_Value / (1 + WACC)^n
```

**Total Fair Value:**
```
Enterprise_Value = PV_Stage1 + PV_Stage2 + PV_Terminal
Equity_Value = Enterprise_Value - Net_Debt
Fair_Value_per_Share = Equity_Value / Shares_Outstanding
```

## When to Use

### Ideal Candidates

**High-Growth Companies:**
- Tech companies transitioning to maturity
- Fast-growing consumer brands
- Emerging market champions
- Companies with 15-30% current growth

**Characteristics:**
- Unsustainable current growth rates
- Clear path to maturity
- Visible competitive advantages
- Capital-light business models

### Real-World Examples

**Technology:**
- Netflix (high growth → maturing streaming)
- Shopify (e-commerce platform scaling)
- Software companies post-IPO

**Consumer:**
- Chipotle (unit expansion → mature footprint)
- Starbucks (international growth → saturation)

**Healthcare:**
- Biotech post-approval (launch → penetration → maturity)

## Advantages Over Single-Stage DCF

### 1. Realistic Growth Assumptions
Single-stage assumes 20% growth forever (impossible)
Multi-stage models inevitable slowdown

### 2. Captures Lifecycle
Explicitly values transition from growth to maturity

### 3. Better Terminal Value
Terminal growth rate is believable (3-4% vs 15%)

### 4. Flexible Modeling
Can adjust each stage independently based on analysis

## Implementation

### Parameter Selection

**Stage 1 Growth (High Growth Phase):**
- **Basis**: Historical growth, analyst estimates, market opportunity
- **Duration**: 5-7 years (longer for younger companies)
- **Typical Rates**: 15-30% for tech, 10-20% for consumer

**Stage 2 Transition:**
- **Basis**: Industry maturation rates
- **Duration**: 5-7 years
- **Pattern**: Linear decline, S-curve, or step-down

**Stage 3 Terminal Growth:**
- **Basis**: GDP growth + inflation (2-4%)
- **Duration**: Forever (perpetuity)
- **Max Rate**: Must be < WACC, typically ≤ 4%

### Code Example

```python
from invest.valuation.multi_stage_dcf import MultiStageDCF

# Initialize
dcf = MultiStageDCF()

# Define growth stages
stages = [
    {'years': 5, 'growth_rate': 0.20},   # High growth
    {'years': 5, 'growth_rate': 0.10},   # Transition
    {'terminal': True, 'growth_rate': 0.03}  # Perpetuity
]

# Calculate
result = dcf.calculate_fair_value(
    stock_data=stock_data,
    growth_stages=stages,
    wacc=0.09
)

print(f'Stage 1 Value: ${result["stage1_pv"]:.2f}')
print(f'Stage 2 Value: ${result["stage2_pv"]:.2f}')
print(f'Terminal Value: ${result["terminal_pv"]:.2f}')
print(f'Fair Value: ${result["fair_value"]:.2f}')
```

## Critical Assumptions

### 1. Growth Rate Decline Path

**Linear Decline (Simple):**
```python
g_t = g_high - (g_high - g_terminal) * (t / total_years)
```

**S-Curve (Realistic):**
Growth stays high longer, then drops faster
```python
# Logistic function
g_t = g_terminal + (g_high - g_terminal) / (1 + e^(k*(t-midpoint)))
```

**Step-Down (Conservative):**
```python
if t <= 5: g = 0.20
elif t <= 10: g = 0.10
else: g = 0.03
```

### 2. WACC Over Time

**Simple Approach:** Constant WACC across all stages

**Sophisticated Approach:**
- Higher WACC in high-growth phase (more risk)
- Lower WACC in mature phase (less risk)

```python
wacc_stage1 = 0.12  # Higher risk
wacc_stage2 = 0.10  # Moderate risk
wacc_stage3 = 0.08  # Lower risk (mature)
```

### 3. Terminal Value Sensitivity

**Terminal value typically 60-80% of total value**

Sensitivity to terminal growth:
```
g_terminal = 2% → Fair Value = $100
g_terminal = 3% → Fair Value = $120 (+20%)
g_terminal = 4% → Fair Value = $150 (+50%)
```

**Sanity checks:**
- Terminal FCF margin reasonable vs industry
- Implied terminal EV/EBITDA multiple realistic
- Terminal ROIC > WACC (value creation)

## Common Mistakes

### 1. Overly Optimistic Stage 1

**Error:** Assuming 40% growth for 10 years
**Reality:** Very few companies sustain >20% for 5+ years

**Fix:** Use historical data + market size constraints

### 2. Too-High Terminal Growth

**Error:** 6% terminal growth (implies dominating global GDP)
**Reality:** GDP + inflation ≈ 3-4% max

**Fix:** Never exceed long-term GDP growth

### 3. Ignoring Mean Reversion

**Error:** High margins sustained forever
**Reality:** Competition erodes excess returns

**Fix:** Model margin compression in Stage 2

### 4. Inconsistent Reinvestment

**Error:** High growth without CapEx/working capital
**Reality:** Growth requires investment

**Fix:** FCF = NOPAT - (Growth × Reinvestment_Rate)

## Sector Applications

### Technology (Software/Internet)

**Typical Structure:**
- Stage 1 (5 years): 25% growth
- Stage 2 (5 years): 25% → 5% linear decline
- Terminal: 3% perpetuity

**Key Drivers:**
- TAM penetration
- Market share gains
- Platform effects
- Margin expansion (economies of scale)

### Consumer Discretionary

**Typical Structure:**
- Stage 1 (7 years): 15% growth
- Stage 2 (7 years): 15% → 3% decline
- Terminal: 3% perpetuity

**Key Drivers:**
- Store/unit expansion
- Same-store sales growth
- International expansion
- Brand strength

### Healthcare/Biotech

**Typical Structure:**
- Stage 1 (5 years): 30% growth (post-drug approval)
- Stage 2 (5 years): 30% → 4% (peak sales → generic threat)
- Terminal: 2% perpetuity

**Key Drivers:**
- Drug adoption curve
- Market penetration
- Patent cliff timing
- Pipeline value

## Comparison to Other DCF Variants

| Model | Growth Assumption | Best For | Complexity |
|-------|------------------|----------|------------|
| **Single-Stage DCF** | Constant forever | Mature, stable companies | Low |
| **Two-Stage DCF** | High then terminal | Simple growth slowdown | Medium |
| **Multi-Stage DCF** | Multiple phases | Growth companies | High |
| **H-Model** | Linear decline | Mathematical elegance | Medium |
| **Growth DCF** | CapEx separation | Reinvestment-heavy | Medium |

## Academic Foundation

### Core Theory

**Gordon Growth Model (1956):**
- Foundation for terminal value perpetuity
- P = D / (r - g)

**Damodaran (2002): Investment Valuation**
- Comprehensive treatment of multi-stage models
- Sector-specific growth patterns

### Empirical Evidence

**Chan, Karceski & Lakonishok (2003):**
- "The Level and Persistence of Growth Rates"
- High growth rates mean-revert within 5-7 years
- Justifies multi-stage approach

**Fama & French (2000):**
- "Forecasting Profitability and Earnings"
- Profit margins revert to industry mean
- Supports modeling margin compression

## Advanced Techniques

### 1. DCF with Real Options

Add option value for:
- Expansion options (new markets)
- Abandonment options (exit strategy)
- Flexibility options (pivot ability)

### 2. Scenario-Based Multi-Stage

Instead of single forecast, use weighted scenarios:
```
Fair_Value = 0.3 × Bull_Case + 0.5 × Base_Case + 0.2 × Bear_Case
```

### 3. Bayesian Updating

Update growth assumptions as new data arrives:
- Quarterly earnings → revise Stage 1 growth
- Management guidance → adjust transition timing
- Competitive dynamics → modify terminal assumptions

## Limitations

### 1. Forecast Uncertainty

Predicting growth 10+ years out is extremely difficult

**Mitigation:** Sensitivity analysis, scenario planning

### 2. Terminal Value Dominance

Still 60-80% of value in terminal period

**Mitigation:** Sanity-check terminal multiples and ROIC

### 3. Parameter Sensitivity

Small changes in WACC or g_terminal → large value changes

**Mitigation:** Monte Carlo simulation, range of estimates

### 4. Circular Logic Risk

Using current valuation to justify future growth

**Mitigation:** Bottom-up forecasts, external benchmarks

## When to Use

### Primary Valuation Method
- High-growth companies with visible maturation path
- Companies in transition (post-IPO, market expansion)
- Situations where single-stage DCF unrealistic

### Cross-Check with Other Models
- Compare terminal multiples to peer averages
- Validate with GBM ranking (relative attractiveness)
- Triangulate with Simple Ratios for sanity check

### Avoid
- Extremely uncertain businesses (early biotech, startups)
- Cyclical companies (use normalized earnings instead)
- Financial institutions (use RIM instead)

## Practical Workflow

### Step 1: Assess Growth Sustainability
```python
# Check historical growth rates
revenue_growth_5y = (revenue_now / revenue_5y_ago)^(1/5) - 1
fcf_growth_5y = (fcf_now / fcf_5y_ago)^(1/5) - 1

# Compare to market TAM
market_share_potential = TAM / current_revenue
years_to_maturity = log(market_share_target) / log(1 + growth_rate)
```

### Step 2: Define Stages
```python
if years_to_maturity < 5:
    # Two-stage model sufficient
    stages = [5, terminal]
elif years_to_maturity < 10:
    # Three-stage model
    stages = [5, 5, terminal]
else:
    # Extended multi-stage
    stages = [5, 5, 5, terminal]
```

### Step 3: Set Growth Rates
```python
# Stage 1: Use analyst consensus or historical growth
g_stage1 = min(analyst_consensus, historical_5y * 1.2)

# Stage 2: Linear decline to GDP growth
g_stage2_start = g_stage1
g_stage2_end = gdp_growth + inflation

# Terminal: Conservative GDP growth
g_terminal = 0.03
```

### Step 4: Calculate and Validate
```python
result = multi_stage_dcf.calculate(stages, growth_rates, wacc)

# Validation checks
terminal_ev_ebitda = result['terminal_value'] / terminal_ebitda
assert terminal_ev_ebitda < 15, 'Terminal multiple too high'

terminal_roic = terminal_nopat / terminal_invested_capital
assert terminal_roic > wacc, 'Terminal value destroying value'
```

## References

- Chan, L., Karceski, J., & Lakonishok, J. (2003). "The Level and Persistence of Growth Rates". *Journal of Finance*.
- Damodaran, A. (2002). *Investment Valuation: Tools and Techniques for Determining the Value of Any Asset*. Wiley.
- Fama, E., & French, K. (2000). "Forecasting Profitability and Earnings". *Journal of Business*.
- Fuller, R., & Hsia, C. (1984). "A Simplified Common Stock Valuation Model". *Financial Analysts Journal*.
- Gordon, M. (1956). "The Investment, Financing, and Valuation of the Corporation". *Brookings Institution*.

## See Also

- **[DCF Model](dcf.md)**: Single-stage foundation
- **[Growth DCF](growth-dcf.md)**: CapEx-adjusted variant
- **[Enhanced DCF](dcf-enhanced.md)**: Dividend-adjusted variant
- **[GBM Full](gbm-full.md)**: Machine learning alternative for relative ranking
