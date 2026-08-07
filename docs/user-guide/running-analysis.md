# Running Analysis

This guide covers how to execute stock analysis using the Systematic Investment Analysis Framework.

## Basic Execution

### Command Structure

```bash
uv run python scripts/systematic_analysis.py [CONFIG_FILE] [OPTIONS]
```

### Quick Examples

```bash
# Use default configuration
uv run python scripts/systematic_analysis.py

# Analyze specific configuration with CSV output
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv

# Run with all output formats
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv --save-json --output results/
```

## Available Configurations

List all available configurations:

```bash
uv run python scripts/systematic_analysis.py --list-configs
```

### Pre-built Configurations

| Configuration | Description | Stocks | Runtime |
|---------------|-------------|---------|---------|
| `sp500_full.yaml` | Complete S&P 500 analysis | ~503 | 10-15 min |
| `sp500_subset.yaml` | Top 20 S&P 500 stocks | 20 | 2-3 min |
| `test_tech_giants.yaml` | TSLA, AAPL, GOOGL | 3 | 30 sec |
| `conservative_value.yaml` | Value-focused screening | Variable | 5-10 min |
| `aggressive_growth.yaml` | Growth-focused screening | Variable | 5-10 min |

## Command Line Options

### Output Options

| Option | Description |
|--------|-------------|
| `--save-csv` | Export results in CSV format |
| `--save-json` | Export raw data in JSON format |
| `--output DIR` | Specify output directory |

### Execution Options

| Option | Description |
|--------|-------------|
| `--quiet` | Suppress progress output |
| `--verbose` | Show detailed logging |

### Utility Options

| Option | Description |
|--------|-------------|
| `--list-configs` | Show available configurations |
| `--create-example FILE` | Create example configuration |

## Background Execution

For long-running analyses, use background execution:

```bash
# Run in background
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv --quiet &

# Monitor progress
tail -f sp500_full_screen_*_report.txt

# Check if still running
ps aux | grep systematic_analysis
```

## Output Files

### Naming Convention

Files are automatically named with timestamps:
```
{config_name}_{timestamp}_{type}.{extension}
```

Examples:
- `sp500_full_screen_20240818_123456_report.txt`
- `sp500_full_screen_20240818_123456_results.csv`
- `sp500_full_screen_20240818_123456_data.json`

### File Locations

By default, files are saved in the current directory. Use `--output` to specify a different location:

```bash
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv --output ~/investment_results/
```

## Performance Considerations

### Runtime Estimates

| Stock Count | Typical Runtime |
|-------------|----------------|
| 1-10 stocks | 30-60 seconds |
| 20-50 stocks | 2-5 minutes |
| 100 stocks | 5-10 minutes |
| 500+ stocks | 10-15 minutes |

### Memory Usage

- **Basic analysis**: ~100-200 MB
- **Full S&P 500**: ~500-800 MB
- **With valuation models**: +50-100 MB

### Network Requirements

The framework fetches data from Yahoo Finance:
- ~10-20 API calls per stock
- Automatic rate limiting
- Retry logic for failed requests

## Error Handling

### Common Errors and Solutions

**Configuration file not found**:
```bash
ERROR: Configuration file not found: dashboard/configs/my_config.yaml
```
Solution: Verify the file path and ensure the file exists.

**Network timeout**:
```bash
WARNING: Failed to get data for AAPL: HTTPSConnectionPool timeout
```
Solution: This is normal for a few stocks. The analysis will continue with available data.

**Permission denied**:
```bash
ERROR: Permission denied: /protected/directory/
```
Solution: Use `--output` to specify a writable directory.

### Data Quality Issues

**Missing financial data**:
- Some stocks may have incomplete financial information
- The framework handles missing data gracefully
- Results will indicate data availability

**Stale data**:
- Yahoo Finance data may have delays
- Consider running analysis after market close for most recent data

## Progress Monitoring

### Verbose Output

Use `--verbose` for detailed progress information:

```bash
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --verbose
```

Shows:
- Individual stock processing status
- Screening results for each stock
- Detailed error messages
- Performance timing information

### Quiet Mode

Use `--quiet` to minimize output:

```bash
uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --quiet
```

Only shows:
- Final summary statistics
- Critical error messages
- File save confirmations

## Batch Processing

### Multiple Configurations

Run multiple analyses in sequence:

```bash
#!/bin/bash
configs=("conservative_value" "aggressive_growth" "sp500_full")

for config in "${configs[@]}"; do
    echo "Running analysis: $config"
    uv run python scripts/systematic_analysis.py "dashboard/configs/${config}.yaml" --save-csv --quiet
done
```

### Scheduled Execution

For regular analysis updates, use cron jobs:

```bash
# Add to crontab (crontab -e)
# Run analysis every Sunday at 8 PM
0 20 * * 0 cd /path/to/invest && uv run python scripts/systematic_analysis.py dashboard/configs/sp500_full.yaml --save-csv --quiet
```

## Next Steps

- **[Understanding Results](understanding-results.md)** - Interpret analysis output
- **[Configuration Options](configuration-options.md)** - Customize analysis parameters
- **[Output Formats](output-formats.md)** - Work with generated data