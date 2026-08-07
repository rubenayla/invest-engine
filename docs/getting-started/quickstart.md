# Quick Start

Get up and running with the Systematic Investment Analysis Framework in 5 minutes.

## Basic Usage

!!! warning "Important"
    **Always use `uv run` for all commands** - This project requires UV dependency management.

### 1. Your First Analysis

Run a simple analysis on major tech companies:

```bash
uv run python scripts/systematic_analysis.py dashboard/configs/test_tech_giants.yaml --save-csv
```

This will:
- Analyze Tesla, Apple, and Google
- Apply screening criteria
- Generate a report and CSV file

### 2. View Results

Check the generated files:

```bash
# View the summary report
cat tech_giants_test_*_report.txt

# View CSV data
cat tech_giants_test_*_results.csv
```

### 3. Full S&P 500 Analysis

!!! tip "Background Execution"
    The full S&P 500 analysis takes 10-15 minutes. Run it in the background:

```bash
# Run full S&P 500 analysis
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv --quiet &

# Monitor progress
tail -f sp500_full_screen_*_report.txt
```

## Understanding the Output

### CSV Results

The CSV output includes these key columns:

| Column | Description |
|--------|-------------|
| `Ticker` | Stock symbol |
| `Passes_Filters` | Y/N - Whether stock meets all criteria |
| `Composite_Score` | Overall score (0-100) |
| `Quality_Score` | Financial quality score |
| `Value_Score` | Valuation attractiveness |
| `Growth_Score` | Growth prospects |
| `Risk_Score` | Risk assessment |

### Example Output

```csv
Ticker,Sector,Market_Cap_B,Current_Price,Passes_Filters,Composite_Score,Quality_Score,Value_Score,Growth_Score,Risk_Score
GOOGL,Communication Services,2471.45,203.90,Y,98.9,100.0,100.0,100.0,7.2
AAPL,Technology,3436.89,231.59,N,57.9,75.0,0.0,100.0,30.6
TSLA,Consumer Cyclical,1066.20,330.56,N,28.6,50.0,0.0,0.0,9.0
```

**Key Insights:**
- Google passes all filters with a high composite score (98.9)
- Apple fails filters due to valuation concerns (P/B ratio too high)
- Tesla fails due to both quality and value concerns

## Available Configurations

List all available configurations:

```bash
uv run python scripts/systematic_analysis.py --list-configs
```

Common configurations:

- `sp500_full.yaml` - Full S&P 500 analysis
- `sp500_subset.yaml` - Top 20 S&P 500 stocks
- `test_tech_giants.yaml` - Tesla, Apple, Google analysis

## Command Line Options

```bash
# Basic usage
uv run python scripts/systematic_analysis.py [config_file]

# With options
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml \
  --save-csv \
  --save-json \
  --output results/ \
  --quiet
```

### Options Reference

| Option | Description |
|--------|-------------|
| `--save-csv` | Export results in CSV format |
| `--save-json` | Export raw data in JSON format |
| `--output DIR` | Specify output directory |
| `--quiet` | Suppress progress output |
| `--verbose` | Show detailed logging |
| `--list-configs` | Show available configurations |

## Interpreting Results

### Filter Status

**Passes_Filters = Y**: Stock meets all screening criteria and is recommended for further analysis.

**Passes_Filters = N**: Stock fails one or more criteria. Common reasons:
- Low ROE/ROIC (quality issues)
- High P/E or P/B ratios (overvalued)
- Negative growth (declining business)
- High debt levels (financial risk)

### Composite Scores

- **90-100**: Exceptional stocks meeting all criteria with strong metrics
- **70-89**: Good stocks with minor weaknesses
- **50-69**: Average stocks with notable concerns
- **Below 50**: Stocks with significant issues

## Next Steps

- **[Configuration Guide](configuration.md)** - Customize screening criteria
- **[User Guide](../user-guide/overview.md)** - Detailed usage instructions
- **[Understanding Results](../user-guide/understanding-results.md)** - In-depth result interpretation

## Common Workflows

### Find Value Opportunities

```bash
# Look for undervalued quality companies
uv run python scripts/systematic_analysis.py dashboard/configs/conservative_value.yaml --save-csv
```

### Growth Stock Screening

```bash
# Focus on high-growth companies
uv run python scripts/systematic_analysis.py dashboard/configs/aggressive_growth.yaml --save-csv
```

### Custom Analysis

1. Copy an existing config: `cp dashboard/configs/sp500_full.yaml dashboard/configs/my_strategy.yaml`
2. Edit the criteria in `dashboard/configs/my_strategy.yaml`
3. Run: `uv run python scripts/systematic_analysis.py dashboard/configs/my_strategy.yaml --save-csv`

## 🤖 Using with AI Assistants

Instead of running commands manually, you can instruct your AI assistant to use the framework. Here are practical examples:

### Example Prompts for AI

**Get Started with Screening:**
```
I want to find the best investment opportunities right now. Please screen the S&P 500 using conservative value criteria and show me the top 10 stocks with explanations of why they're attractive.
```

**International Opportunities:**
```
Warren Buffett has been investing in Japan recently. Please analyze the Japanese market using the japan_buffett_favorites configuration and explain why these companies might be undervalued.
```

**Deep Dive on Specific Stocks:**
```
I'm interested in Microsoft (MSFT). Please run it through the systematic screening and give me your detailed analysis - does it pass the filters, what are its strengths and weaknesses, and should I invest?
```

**Sector Analysis:**
```
I want to invest in the technology sector but need help finding quality companies at reasonable prices. Please screen tech stocks and recommend the best opportunities.
```

**Portfolio Construction:**
```
Please analyze the market and build me a diversified portfolio of 15-20 stocks. Focus on quality companies trading at reasonable valuations with good growth prospects.
```

**Market Comparison:**
```
Compare investment opportunities between US and international markets. Where can I find better value right now - S&P 500 or Japanese stocks?
```

**Follow-up Analysis:**
```
Looking at the screening results, can you explain why Tesla failed the filters while Google passed? What would need to change for Tesla to become attractive?
```

### What Happens When You Ask

Your AI assistant will:

1. **Execute the screening** using appropriate configuration files
2. **Analyze results** and identify key patterns and opportunities  
3. **Provide detailed explanations** of why stocks passed or failed filters
4. **Give investment recommendations** based on the systematic analysis
5. **Answer follow-up questions** about specific companies or strategies
6. **Generate custom reports** tailored to your investment goals

### AI-Powered Research Process

The AI handles the complete workflow automatically:
- Fetches and processes stock data for hundreds of companies
- Applies systematic quality, value, growth, and risk filters
- Calculates composite scores and rankings
- Identifies the most promising investment opportunities
- Provides detailed analysis of individual companies
- Generates actionable investment recommendations

This gives you the power of systematic analysis with the convenience of conversational AI interaction.