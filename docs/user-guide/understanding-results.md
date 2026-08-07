# Understanding Results

Learn how to interpret the output from the Systematic Investment Analysis Framework.

## Result Overview

The framework generates comprehensive results in multiple formats. Here's how to understand what each component means.

## CSV Output Structure

### Key Columns

| Column | Range | Description |
|--------|-------|-------------|
| `Ticker` | Text | Stock symbol (e.g., AAPL, GOOGL) |
| `Sector` | Text | Business sector classification |
| `Market_Cap_B` | Number | Market capitalization in billions USD |
| `Current_Price` | Number | Current stock price in USD |
| `Passes_Filters` | Y/N | Whether stock meets all screening criteria |
| `Composite_Score` | 0-100 | Overall investment attractiveness score |
| `Quality_Score` | 0-100 | Financial strength and stability score |
| `Value_Score` | 0-100 | Valuation attractiveness score |
| `Growth_Score` | 0-100 | Business growth prospects score |
| `Risk_Score` | 0-100 | Risk level (lower is better) |

### Financial Metrics

| Column | Description |
|--------|-------------|
| `P_E` | Price-to-Earnings ratio |
| `P_B` | Price-to-Book ratio |
| `ROE` | Return on Equity (decimal format) |
| `ROIC` | Return on Invested Capital (decimal format) |
| `Revenue_Growth` | Revenue growth rate (decimal format) |
| `Debt_Equity` | Debt-to-Equity ratio |

## Score Interpretation

### Composite Score (0-100)

The composite score combines all dimensions:

- **90-100**: Exceptional stocks - Strong across all metrics
- **80-89**: Very good stocks - Minor weaknesses only
- **70-79**: Good stocks - Some areas of concern
- **60-69**: Average stocks - Notable issues present
- **50-59**: Below average - Significant weaknesses
- **Below 50**: Poor stocks - Multiple serious issues

### Individual Score Dimensions

#### Quality Score (0-100)
Measures financial strength and business stability:

- **90-100**: Excellent - Strong ROE/ROIC, low debt, good liquidity
- **70-89**: Good - Solid fundamentals with minor concerns
- **50-69**: Average - Acceptable quality but room for improvement
- **30-49**: Poor - Weak fundamentals, higher risk
- **Below 30**: Very poor - Significant financial issues

**Key factors:**
- Return on Equity (ROE)
- Return on Invested Capital (ROIC)
- Debt-to-equity ratio
- Current ratio (liquidity)

#### Value Score (0-100)
Assesses whether stock is attractively priced:

- **90-100**: Excellent value - Trading below intrinsic worth
- **70-89**: Good value - Reasonable pricing
- **50-69**: Fair value - Appropriately priced
- **30-49**: Expensive - Trading above fair value
- **Below 30**: Very expensive - Significantly overvalued

**Key factors:**
- Price-to-Earnings ratio
- Price-to-Book ratio
- EV/EBITDA multiple
- Price-to-Free Cash Flow

#### Growth Score (0-100)
Evaluates business expansion and future prospects:

- **90-100**: Exceptional growth - Strong, sustainable expansion
- **70-89**: Good growth - Solid business momentum
- **50-69**: Moderate growth - Steady but unremarkable
- **30-49**: Slow growth - Limited expansion
- **Below 30**: Declining - Shrinking business

**Key factors:**
- Revenue growth rate
- Earnings growth rate
- Free cash flow growth
- Market expansion potential

#### Risk Score (0-100)
Assesses investment risk levels (lower is better):

- **0-20**: Very low risk - Stable, predictable business
- **21-40**: Low risk - Some variability but manageable
- **41-60**: Moderate risk - Normal business volatility
- **61-80**: High risk - Significant uncertainties
- **Above 80**: Very high risk - Highly unpredictable

**Key factors:**
- Stock price volatility (beta)
- Financial leverage
- Business model stability
- Sector-specific risks

## Filter Status Analysis

### Passes_Filters = Y (Yes)

Stock meets all minimum thresholds:

**Quality Requirements Met:**
- ✅ ROE ≥ minimum threshold
- ✅ ROIC ≥ minimum threshold  
- ✅ Debt levels within acceptable range
- ✅ Adequate liquidity ratios

**Value Requirements Met:**
- ✅ P/E ratio ≤ maximum threshold
- ✅ P/B ratio ≤ maximum threshold
- ✅ Other valuation metrics acceptable

**Growth Requirements Met:**
- ✅ Revenue growth ≥ minimum threshold
- ✅ Earnings growth ≥ minimum threshold

**Risk Requirements Met:**
- ✅ Beta ≤ maximum threshold
- ✅ Overall risk score acceptable

### Passes_Filters = N (No)

Stock fails one or more criteria. Common failure reasons:

#### Quality Failures
- **Low ROE/ROIC**: Poor profitability and capital efficiency
- **High debt levels**: Excessive financial leverage
- **Poor liquidity**: Insufficient short-term assets

#### Value Failures  
- **High P/E ratio**: Stock trading at premium multiple
- **Excessive P/B ratio**: Price significantly above book value
- **Rich valuations**: Multiple metrics suggest overvaluation

#### Growth Failures
- **Declining revenues**: Business is shrinking
- **Negative earnings growth**: Profitability decreasing
- **Stagnant business**: No meaningful expansion

#### Risk Failures
- **High volatility**: Stock price very unpredictable
- **Excessive leverage**: Dangerous debt levels
- **Sector concerns**: Industry-specific risks

## Sector Comparisons

### Sector Benchmarks

Different sectors have different normal ranges:

#### Technology Sector
- **Typical P/E**: 20-40 (higher acceptable)
- **Expected Growth**: 10-30% revenue growth
- **Debt Tolerance**: Generally lower debt levels
- **Volatility**: Higher beta acceptable (1.2-1.8)

#### Utilities Sector
- **Typical P/E**: 15-25 (lower range)
- **Expected Growth**: 2-8% revenue growth
- **Debt Tolerance**: Higher debt acceptable
- **Volatility**: Lower beta expected (0.6-1.0)

#### Financial Sector
- **Metrics Differ**: Different debt interpretation
- **Interest Sensitivity**: Rate environment crucial
- **Regulatory Impact**: Capital requirements matter

### Cross-Sector Analysis

When comparing stocks from different sectors:

1. **Focus on relative performance** within each sector
2. **Consider sector-specific factors** (growth vs. stability)
3. **Adjust expectations** based on business models
4. **Account for cyclical patterns** in commodity/cyclical sectors

## Example Analysis

Let's analyze sample results:

```csv
Ticker,Sector,Passes_Filters,Composite_Score,Quality_Score,Value_Score,Growth_Score,Risk_Score
GOOGL,Communication Services,Y,98.9,100.0,100.0,100.0,7.2
AAPL,Technology,N,57.9,75.0,0.0,100.0,30.6
TSLA,Consumer Cyclical,N,28.6,50.0,0.0,0.0,9.0
```

### Google (GOOGL) - Score: 98.9
✅ **Passes all filters**
- **Quality**: Excellent (100.0) - Strong ROE, ROIC, low debt
- **Value**: Excellent (100.0) - Attractive valuation metrics
- **Growth**: Excellent (100.0) - Strong revenue/earnings growth
- **Risk**: Very low (7.2) - Stable, predictable business

**Investment Thesis**: High-quality growth company at reasonable valuation

### Apple (AAPL) - Score: 57.9
❌ **Fails value filters**
- **Quality**: Good (75.0) - Solid fundamentals but not exceptional
- **Value**: Poor (0.0) - **Overvalued** - High P/B ratio, expensive metrics
- **Growth**: Excellent (100.0) - Strong business momentum
- **Risk**: Moderate (30.6) - Some volatility but manageable

**Investment Thesis**: Great company but expensive - wait for better entry

### Tesla (TSLA) - Score: 28.6
❌ **Fails multiple filters**
- **Quality**: Poor (50.0) - **Low ROE/ROIC** - Capital efficiency concerns
- **Value**: Poor (0.0) - **Highly overvalued** - Excessive P/E ratio
- **Growth**: Poor (0.0) - **Declining revenues** - Business momentum lost
- **Risk**: Very low (9.0) - Interestingly, low volatility recently

**Investment Thesis**: Multiple red flags - avoid until fundamentals improve

## Red Flags to Watch

### Quality Red Flags
- ROE below 10% (0.10 in decimal format)
- ROIC below 8% (0.08 in decimal format)
- Debt-to-equity above 200% (high leverage)
- Current ratio below 1.0 (liquidity concerns)

### Value Red Flags
- P/E ratio above 40 (unless high-growth justified)
- P/B ratio above 10 (asset-heavy businesses)
- Multiple valuation metrics in expensive range

### Growth Red Flags
- Negative revenue growth for multiple periods
- Declining profit margins
- Market share loss to competitors

### Risk Red Flags
- Beta above 2.0 (very high volatility)
- Excessive debt in cyclical industries
- Single customer/geographic concentration

## Using Results for Investment Decisions

### Stock Selection Process

1. **Filter by Pass/Fail**: Start with stocks that pass all filters
2. **Rank by Composite Score**: Focus on highest-scoring opportunities
3. **Sector Diversification**: Don't concentrate in single sector
4. **Individual Analysis**: Review specific metrics for each candidate
5. **Qualitative Research**: Supplement quantitative analysis

### Portfolio Construction Guidelines

**Core Holdings (70-80% of portfolio):**
- Composite Score ≥ 80
- Passes all filters
- Quality Score ≥ 70

**Opportunistic Holdings (10-20% of portfolio):**
- Composite Score 60-79
- May fail 1-2 filters with good reason
- Higher potential upside

**Avoid (0-10% speculative only):**
- Composite Score < 60
- Fails multiple filters
- Significant red flags present

## Next Steps

- **[Configuration Options](configuration-options.md)** - Adjust screening criteria
- **[Output Formats](output-formats.md)** - Work with different data formats
- **[Running Analysis](running-analysis.md)** - Execute comprehensive analysis