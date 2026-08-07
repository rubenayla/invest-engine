# Output Formats

The Systematic Investment Analysis Framework generates results in multiple formats. This guide explains each format and how to use them effectively.

## Available Output Formats

### 1. Text Report (Default)
- **File**: `{config_name}_{timestamp}_report.txt`
- **Content**: Human-readable comprehensive analysis
- **Use Case**: Executive summary and detailed stock analysis

### 2. CSV Export (--save-csv)
- **File**: `{config_name}_{timestamp}_results.csv`
- **Content**: Structured data with all metrics
- **Use Case**: Spreadsheet analysis, data manipulation

### 3. JSON Export (--save-json)
- **File**: `{config_name}_{timestamp}_data.json`
- **Content**: Complete raw data and metadata
- **Use Case**: API integration, custom analysis tools

## Text Report Format

### Executive Summary Section

```text
EXECUTIVE SUMMARY
================
Analysis: sp500_full_screen
Date: 2024-08-18 12:32
Description: A screen of all S&P 500 companies.

RESULTS OVERVIEW
---------------
• Total Universe Screened: 503 stocks
• Passed Initial Screening: 45 stocks  
• Final Recommendations: 25 stocks
• Success Rate: 5.0%

AVERAGE QUALITY METRICS
----------------------
• Quality Score: 78.2/100
• Value Score: 65.4/100
• Growth Score: 58.9/100
• Risk Score: 42.1/100

TOP RECOMMENDATIONS
------------------
1. GOOGL - Score: 98.9 (Communication Services)
2. MSFT - Score: 94.2 (Technology)
3. AAPL - Score: 87.6 (Technology)
4. JNJ - Score: 85.3 (Healthcare)
5. PG - Score: 82.9 (Consumer Defensive)

SECTOR BREAKDOWN
---------------
• Technology: 8 stocks
• Healthcare: 6 stocks
• Financial Services: 5 stocks
• Consumer Defensive: 4 stocks
• Communication Services: 2 stocks

KEY INSIGHTS
-----------
• Found 25 stocks meeting criteria
• Average composite score: 79.8
• Most represented sector: Technology
```

### Detailed Stock Analysis

For each stock that passes filters:

```text
DETAILED ANALYSIS: GOOGL
==================================================

COMPANY OVERVIEW
---------------
• Sector: Communication Services
• Industry: Internet Content & Information
• Market Cap: $2462.65B
• Current Price: $203.34

COMPOSITE SCORING
• Overall Score: 98.9/100
• Quality Score: 100.0/100
• Value Score: 100.0/100  
• Growth Score: 100.0/100
• Risk Score: 7.2/100

QUALITY ASSESSMENT
-----------------
• Return on Equity: 34.8%
• Return on Invested Capital: 31.2%
• Current Ratio: 1.90
• Debt to Equity: 11.5%
• Quality Rating: EXCELLENT

VALUATION ANALYSIS
-----------------
• P/E Ratio: 21.7
• P/B Ratio: 6.80
• EV/EBITDA: 17.1
• Valuation Rating: ATTRACTIVE

GROWTH EVALUATION
----------------
• Revenue Growth: 13.8%
• Earnings Growth: 22.3%
• Growth Quality: STRONG
• Growth Sustainability: HIGH

RISK ASSESSMENT
--------------
• Risk Level: LOW
• Beta: 1.05 (estimated)
• Financial Risk: VERY LOW
• Business Risk: LOW
• Sector Risk: MODERATE
```

## CSV Format Structure

### Column Definitions

```csv
Ticker,Sector,Market_Cap_B,Current_Price,Passes_Filters,Composite_Score,Quality_Score,Value_Score,Growth_Score,Risk_Score,P_E,P_B,ROE,ROIC,Revenue_Growth,Debt_Equity
```

### Data Types and Formats

| Column | Data Type | Format | Example |
|--------|-----------|--------|---------|
| `Ticker` | String | Text | AAPL |
| `Sector` | String | Text | Technology |
| `Market_Cap_B` | Float | Billions USD | 3436.89 |
| `Current_Price` | Float | USD | 231.59 |
| `Passes_Filters` | String | Y/N | Y |
| `Composite_Score` | Float | 0-100 | 95.4 |
| `Quality_Score` | Float | 0-100 | 75.0 |
| `Value_Score` | Float | 0-100 | 0.0 |
| `Growth_Score` | Float | 0-100 | 100.0 |
| `Risk_Score` | Float | 0-100 | 30.6 |
| `P_E` | Float | Ratio | 35.1 |
| `P_B` | Float | Ratio | 52.27 |
| `ROE` | Float | Decimal (0.15 = 15%) | 1.498 |
| `ROIC` | Float | Decimal | 0.589 |
| `Revenue_Growth` | Float | Decimal | 0.096 |
| `Debt_Equity` | Float | Percentage | 154.5 |

### Sample CSV Data

```csv
Ticker,Sector,Market_Cap_B,Current_Price,Passes_Filters,Composite_Score,Quality_Score,Value_Score,Growth_Score,Risk_Score,P_E,P_B,ROE,ROIC,Revenue_Growth,Debt_Equity
GOOGL,Communication Services,2471.45,203.90,Y,98.9,100.0,100.0,100.0,7.2,21.7,6.80,0.348,0.312,0.138,11.5
AAPL,Technology,3436.89,231.59,N,57.9,75.0,0.0,100.0,30.6,35.1,52.27,1.498,0.589,0.096,154.5
TSLA,Consumer Cyclical,1066.20,330.56,N,28.6,50.0,0.0,0.0,9.0,195.6,13.78,0.082,0.070,-0.118,16.8
```

## JSON Format Structure

### Complete Data Export

```json
{
  "config": {
    "name": "sp500_full_screen",
    "description": "A screen of all S&P 500 companies.",
    "universe": {
      "pre_screening_universe": "sp500",
      "region": "US",
      "min_market_cap": 100
    },
    "quality": {
      "min_roic": 0.08,
      "min_roe": 0.10,
      "max_debt_equity": 2.0
    }
  },
  "summary": {
    "top_picks": [
      {
        "ticker": "GOOGL",
        "composite_score": 98.9,
        "sector": "Communication Services"
      }
    ],
    "average_scores": {
      "quality": 78.2,
      "value": 65.4,
      "growth": 58.9,
      "risk": 42.1
    },
    "sector_breakdown": {
      "Technology": 8,
      "Healthcare": 6,
      "Financial Services": 5
    },
    "key_insights": [
      "Found 25 stocks meeting criteria",
      "Average composite score: 79.8",
      "Most represented sector: Technology"
    ]
  },
  "stocks": [
    {
      "ticker": "GOOGL",
      "basic_data": {
        "ticker": "GOOGL",
        "market_cap": 2471450000000,
        "sector": "Communication Services",
        "current_price": 203.90
      },
      "scores": {
        "composite": 98.9,
        "quality": 100.0,
        "value": 100.0,
        "growth": 100.0,
        "risk": 7.2
      },
      "passes_filters": true,
      "quality": {
        "quality_score": 100.0,
        "quality_metrics": {
          "roe": 0.348,
          "roic": 0.312,
          "debt_to_equity": 11.5,
          "current_ratio": 1.90
        }
      }
    }
  ],
  "total_universe": 503,
  "passed_screening": 45,
  "final_results": 25
}
```

## Working with Output Files

### Excel/Spreadsheet Analysis

#### Loading CSV Data

1. **Excel**: File → Open → Select CSV file → Import with comma delimiter
2. **Google Sheets**: File → Import → Upload file → Separator: Comma
3. **LibreOffice Calc**: File → Open → Select CSV → Delimiter: Comma

#### Useful Excel Formulas

**Filter for passing stocks only:**
```excel
=FILTER(A:P, E:E="Y")
```

**Calculate sector averages:**
```excel
=AVERAGEIF(B:B, "Technology", F:F)
```

**Rank stocks by composite score:**
```excel
=RANK(F2, F:F, 0)
```

### Python Data Analysis

#### Loading CSV with Pandas

```python
import pandas as pd

# Load results
df = pd.read_csv('sp500_full_screen_20240818_123456_results.csv')

# Filter for passing stocks only
passing_stocks = df[df['Passes_Filters'] == 'Y']

# Top 10 by composite score
top_stocks = df.nlargest(10, 'Composite_Score')

# Sector analysis
sector_stats = df.groupby('Sector').agg({
    'Composite_Score': ['mean', 'count'],
    'Passes_Filters': lambda x: (x == 'Y').sum()
})
```

#### Loading JSON Data

```python
import json
import pandas as pd

# Load complete results
with open('sp500_full_screen_20240818_123456_data.json', 'r') as f:
    results = json.load(f)

# Extract stock data
stocks_df = pd.json_normalize(results['stocks'])

# Get configuration used
config = results['config']
```

### R Data Analysis

```r
library(readr)
library(dplyr)

# Load CSV data
results <- read_csv("sp500_full_screen_20240818_123456_results.csv")

# Filter and analyze
passing_stocks <- results %>%
  filter(Passes_Filters == "Y") %>%
  arrange(desc(Composite_Score))

# Sector breakdown
sector_analysis <- results %>%
  group_by(Sector) %>%
  summarize(
    avg_score = mean(Composite_Score, na.rm = TRUE),
    count = n(),
    passing_count = sum(Passes_Filters == "Y")
  )
```

## Output File Management

### File Naming Convention

Files follow this pattern:
```
{config_name}_{timestamp}_{type}.{extension}
```

Examples:
- `sp500_full_screen_20240818_123456_report.txt`
- `sp500_full_screen_20240818_123456_results.csv`
- `sp500_full_screen_20240818_123456_data.json`

### Organizing Results

Recommended directory structure:
```
investment_analysis/
├── dashboard/configs/
│   ├── my_strategy.yaml
│   └── backup_configs/
├── results/
│   ├── 2024-08/
│   │   ├── sp500_analysis/
│   │   ├── sector_analysis/
│   │   └── custom_screens/
│   └── archive/
└── analysis/
    ├── python_scripts/
    ├── excel_workbooks/
    └── reports/
```

### Batch Processing Results

```bash
# Create organized results structure
mkdir -p results/$(date +%Y-%m)/sp500_analysis

# Run analysis with organized output
uv run python scripts/systematic_analysis.py \
  dashboard/configs/sp500_full.yaml \
  --save-csv --save-json \
  --output results/$(date +%Y-%m)/sp500_analysis/
```

## Custom Output Processing

### Creating Summary Reports

```python
import pandas as pd
from datetime import datetime

def create_summary_report(csv_file):
    """Create custom summary from CSV results."""
    df = pd.read_csv(csv_file)
    
    summary = {
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'total_stocks': len(df),
        'passing_stocks': len(df[df['Passes_Filters'] == 'Y']),
        'top_5_stocks': df.nlargest(5, 'Composite_Score')[['Ticker', 'Composite_Score']].to_dict('records'),
        'sector_breakdown': df['Sector'].value_counts().to_dict(),
        'avg_scores': {
            'composite': df['Composite_Score'].mean(),
            'quality': df['Quality_Score'].mean(),
            'value': df['Value_Score'].mean(),
            'growth': df['Growth_Score'].mean(),
            'risk': df['Risk_Score'].mean()
        }
    }
    
    return summary
```

### Automated Reporting

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def email_results_summary(results_file, recipient):
    """Email analysis results summary."""
    summary = create_summary_report(results_file)
    
    # Create email content
    message = f"""
    Investment Analysis Results - {summary['analysis_date']}
    
    Total Stocks Analyzed: {summary['total_stocks']}
    Stocks Passing Filters: {summary['passing_stocks']}
    Success Rate: {summary['passing_stocks']/summary['total_stocks']*100:.1f}%
    
    Top 5 Recommendations:
    {chr(10).join([f"{i+1}. {stock['Ticker']} ({stock['Composite_Score']:.1f})" for i, stock in enumerate(summary['top_5_stocks'])])}
    
    Average Scores:
    Composite: {summary['avg_scores']['composite']:.1f}
    Quality: {summary['avg_scores']['quality']:.1f}
    Value: {summary['avg_scores']['value']:.1f}
    Growth: {summary['avg_scores']['growth']:.1f}
    Risk: {summary['avg_scores']['risk']:.1f}
    """
    
    # Send email (configure SMTP settings)
    # Implementation details depend on email provider
```

## Integration with External Tools

### Power BI Integration

1. **Data Source**: Use CSV output as data source
2. **Refresh Schedule**: Set up automatic data refresh
3. **Visualizations**: Create dashboards for sector analysis, scoring trends

### Tableau Integration

1. **Connect**: File → Connect → Text file → Select CSV
2. **Data Prep**: Clean and structure data as needed
3. **Visualizations**: Build interactive analysis dashboards

### Database Integration

```sql
-- Create table for results
CREATE TABLE investment_analysis (
    analysis_date DATE,
    ticker VARCHAR(10),
    sector VARCHAR(50),
    market_cap_b DECIMAL(10,2),
    current_price DECIMAL(8,2),
    passes_filters BOOLEAN,
    composite_score DECIMAL(5,2),
    quality_score DECIMAL(5,2),
    value_score DECIMAL(5,2),
    growth_score DECIMAL(5,2),
    risk_score DECIMAL(5,2)
);

-- Load data from CSV
LOAD DATA INFILE 'results.csv' 
INTO TABLE investment_analysis
FIELDS TERMINATED BY ','
LINES TERMINATED BY '\n'
IGNORE 1 ROWS;
```

## Best Practices

### File Management

1. **Consistent naming** - Use descriptive configuration names
2. **Regular archiving** - Move old results to archive folders  
3. **Version control** - Track configuration changes
4. **Backup strategy** - Protect important analysis results

### Data Analysis Workflow

1. **Start with CSV** - Most versatile for initial analysis
2. **Use JSON for integration** - API development and custom tools
3. **Text reports for presentation** - Executive summaries and documentation
4. **Combine formats** - Leverage strengths of each format

### Quality Control

- Validate data completeness before analysis
- Check for obvious errors in results
- Compare results across different time periods
- Verify calculations with manual spot checks

## Next Steps

- **[Running Analysis](running-analysis.md)** - Execute comprehensive analysis
- **[Understanding Results](understanding-results.md)** - Interpret analysis output
- **[Configuration Options](configuration-options.md)** - Customize parameters
