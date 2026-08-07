# Troubleshooting

Common issues and solutions for the Systematic Investment Analysis Framework.

## Installation Issues

### UV Not Found

**Problem**: `uv: command not found`

**Solutions**:
1. **Install UV**: Follow the [official installation guide](https://docs.astral.sh/uv/getting-started/installation/)
2. **Check PATH**: Ensure UV's bin directory is in your PATH
3. **Restart terminal**: Close and reopen your terminal after installation

### Python Version Issues

**Problem**: `Python 3.8+ required`

**Solutions**:
1. **Check version**: `python --version` or `python3 --version`
2. **Install Python 3.8+**: Use your system's package manager or [python.org](https://python.org)
3. **Use specific version**: `uv python pin python3.8`

### Dependency Installation Fails

**Problem**: `uv sync` fails with dependency errors

**Solutions**:
1. **Update UV**: `uv self update`
2. **Clear cache**: `uv cache clean`
3. **Fresh install**: Delete `uv.lock` and run `uv sync`

## Runtime Issues

### Network Timeout Errors

**Problem**: `HTTPSConnectionPool timeout`

**Solutions**:
1. **Normal behavior**: A few timeouts are expected, analysis continues
2. **Check internet**: Ensure stable internet connection
3. **Retry later**: Yahoo Finance may be temporarily unavailable
4. **Use different time**: Try running during off-peak hours

### Configuration File Errors

**Problem**: `Configuration file not found`

**Solutions**:
1. **Check path**: Verify the configuration file exists
2. **Use absolute path**: Provide full path to configuration file
3. **Check working directory**: Ensure you're in the correct directory

**Problem**: `Invalid configuration format`

**Solutions**:
1. **YAML syntax**: Verify YAML formatting (indentation, colons)
2. **Use example**: Start with a working configuration file
3. **Validate online**: Use online YAML validators

### Data Quality Issues

**Problem**: `No data available for ticker`

**Solutions**:
1. **Check ticker**: Verify stock symbol is correct
2. **Market hours**: Some data unavailable during market hours
3. **Delisted stocks**: Remove delisted stocks from custom lists

**Problem**: `Incomplete financial data`

**Solutions**:
1. **Expected behavior**: Some stocks have limited data
2. **Check data age**: Recent IPOs may lack historical data
3. **Alternative tickers**: Try different share classes if available

## Analysis Issues

### No Stocks Pass Filters

**Problem**: Analysis returns no results

**Solutions**:
1. **Relax criteria**: Lower screening thresholds
2. **Check configuration**: Verify parameters are reasonable
3. **Market conditions**: Adjust for current market environment

### Unexpected Results

**Problem**: Expected stocks filtered out

**Solutions**:
1. **Check pass/fail status**: Review why stocks failed filters
2. **Examine individual metrics**: Look at specific screening scores
3. **Adjust thresholds**: Modify configuration parameters

### Performance Issues

**Problem**: Analysis takes too long

**Solutions**:
1. **Reduce universe size**: Use smaller stock lists for testing
2. **Disable valuation models**: Skip DCF/RIM for faster results
3. **Run in background**: Use background execution for large analyses

## Output Issues

### Missing Output Files

**Problem**: Expected files not generated

**Solutions**:
1. **Check output directory**: Verify directory exists and is writable
2. **Use absolute paths**: Specify full output path
3. **Check disk space**: Ensure sufficient disk space available

### Corrupted CSV Files

**Problem**: CSV files unreadable

**Solutions**:
1. **Character encoding**: Try opening with UTF-8 encoding
2. **Excel compatibility**: Use "Text Import Wizard" in Excel
3. **Alternative tools**: Try Google Sheets or LibreOffice Calc

## Common Error Messages

### `cannot access local variable 'margin' where it is not associated with a value`

**Cause**: DCF valuation model error

**Solution**: This has been fixed in recent versions. Update your code or disable DCF models temporarily.

### `'UniverseConfig' object has no attribute 'quality'`

**Cause**: Configuration schema mismatch

**Solution**: Update configuration file format or use provided examples.

### `ModuleNotFoundError: No module named 'invest'`

**Cause**: Package not properly installed

**Solutions**:
1. **Install package**: Run `uv sync`
2. **Check virtual environment**: Ensure using UV environment
3. **Use uv run**: Always prefix commands with `uv run`

## Getting Additional Help

### Documentation Resources

1. **User Guide**: Comprehensive usage documentation
2. **Configuration Guide**: Parameter reference and examples
3. **API Reference**: Technical documentation
4. **Tutorials**: Step-by-step examples

### Community Support

1. **GitHub Issues**: [Report bugs and request features](https://github.com/rubenayla/invest-engine/issues)
2. **Discussions**: Community Q&A and examples
3. **Documentation**: Check this documentation for answers

### Before Reporting Issues

Please provide the following information:

1. **Environment details**:
   - Operating system and version
   - Python version (`python --version`)
   - UV version (`uv --version`)

2. **Error reproduction**:
   - Exact command that failed
   - Complete error message
   - Configuration file used (if relevant)

3. **Expected vs actual behavior**:
   - What you expected to happen
   - What actually happened
   - Any workarounds you've tried

### Debug Mode

For detailed debugging information:

```bash
# Enable verbose logging
uv run python scripts/systematic_analysis.py dashboard/configs/my_config.yaml --verbose

# Python debugging
PYTHONPATH=src python -c "
import invest
print('Package loaded successfully')
print(f'Location: {invest.__file__}')
"
```

## Known Limitations

### Data Source Limitations

- **Yahoo Finance dependency**: Limited to freely available data
- **Rate limiting**: Automatic throttling may slow analysis
- **Data delays**: Real-time data not available
- **International coverage**: Limited non-US stock data

### Valuation Model Limitations

- **Simplified models**: DCF uses basic assumptions
- **Missing data handling**: Some calculations may be skipped
- **Sector adjustments**: Limited sector-specific modeling

### Performance Limitations

- **Memory usage**: Large analyses require significant RAM
- **Processing time**: Full S&P 500 analysis takes 10-15 minutes
- **Network dependency**: Requires stable internet connection

## Best Practices

### Avoid Common Mistakes

1. **Always use `uv run`**: Don't run Python commands directly
2. **Start small**: Test with small stock lists before full analysis
3. **Backup configurations**: Save working configurations before modifications
4. **Regular updates**: Keep dependencies updated with `uv sync --upgrade`

### Optimize Performance

1. **Use background execution** for long analyses
2. **Save intermediate results** with `--save-json`
3. **Monitor memory usage** for large datasets
4. **Run during off-peak hours** for better network performance

## Next Steps

If you can't find a solution here:

1. **Search existing issues**: Check if others have encountered the same problem
2. **Create minimal reproduction**: Simplify your case to the essential problem
3. **Report the issue**: Include all relevant details and debugging information

For feature requests and general questions, use the GitHub Discussions section.