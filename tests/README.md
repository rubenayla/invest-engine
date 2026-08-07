# Investment Analysis Framework - Test Suite

This directory contains comprehensive tests for the Systematic Investment Analysis Framework, ensuring reliability across all components including international markets, AI tools, and valuation models.

## 🧪 Test Suite Overview

### Test Categories

1. **Unit Tests** - Individual component testing
2. **Integration Tests** - Component interaction testing  
3. **End-to-End Tests** - Complete workflow testing
4. **International Market Tests** - Global market functionality
5. **Valuation Model Tests** - DCF and RIM model validation
6. **Configuration Tests** - YAML configuration validation

### Test Files

| File | Purpose | Coverage |
|------|---------|----------|
| `test_data_providers.py` | Data fetching and processing | US & International data sources |
| `test_valuation.py` | Valuation model accuracy | DCF, RIM, sensitivity analysis |
| `test_international_markets.py` | International functionality | Japanese, European markets |
| `test_systematic_analysis.py` | Core analysis pipeline | Screening, filtering, ranking |
| `test_end_to_end.py` | Complete workflows | CLI, configurations, outputs |
| `conftest.py` | Shared fixtures and utilities | Mock data, configurations |

## 🚀 Running Tests

### Quick Test Run

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=src/invest --cov-report=html

# Run specific test file
uv run pytest tests/test_data_providers.py -v

# Run tests by category
uv run pytest -m "unit" -v
uv run pytest -m "international" -v
```

### Comprehensive Test Script

```bash
# Run complete test suite with detailed output
uv run python scripts/run_tests.py
```

### Test Categories by Marker

```bash
# Unit tests only
uv run pytest -m "unit"

# International market tests
uv run pytest -m "international"

# Valuation model tests
uv run pytest -m "valuation"

# Integration tests
uv run pytest -m "integration"

# Skip slow tests
uv run pytest -m "not slow"
```

## 📊 Test Coverage

Target coverage: **80%**

### Coverage Reports

- **Terminal**: Shows missing lines during test run
- **HTML Report**: Generated in `htmlcov/index.html`  
- **XML Report**: Generated as `coverage.xml` for CI/CD

```bash
# Generate coverage reports
uv run pytest --cov=src/invest \
  --cov-report=html \
  --cov-report=term-missing \
  --cov-report=xml
```

## 🌍 International Market Testing

### Japanese Market Tests
- TOPIX Core 30 composition validation
- Berkshire Hathaway holdings verification
- Currency handling (JPY)
- Tokyo Stock Exchange data

### European Market Tests
- FTSE 100 and DAX coverage
- ADR vs local listings
- Multi-currency support (EUR, GBP)

### Test Data
```python
# Japanese stocks
japanese_tickers = ['7203.T', '6758.T', '8306.T']  # Toyota, Sony, Mitsubishi UFJ

# International configurations
configs = ['japan_topix30.yaml', 'international_value.yaml']
```

## 💰 Valuation Model Testing

### DCF Model Tests
- Basic valuation calculations
- Sensitivity analysis
- Edge case handling
- Terminal value methods
- Margin of safety calculations

### RIM Model Tests  
- Residual income calculations
- Book value components
- ROE vs required return analysis

### Test Scenarios
```python
# High-quality growth stock
test_data = {
    'trailing_pe': 25.0,
    'return_on_equity': 0.20,
    'revenue_growth': 0.15,
    'debt_to_equity': 30.0
}
```

## 🔧 Mock Data and Fixtures

### Stock Data Fixtures
- **High-quality US tech stock** (AAPL-like)
- **Value stock** (reasonable metrics)
- **Poor quality stock** (failing criteria)
- **Japanese stocks** (Toyota, Sony)
- **European stocks** (ASML ADR)

### Configuration Fixtures
- Basic US market configuration
- International market configuration
- Value-focused configuration
- Growth-focused configuration

### Data Provider Mocks
```python
@pytest.fixture
def mock_stock_data():
    return {
        'AAPL': {'trailing_pe': 28.5, 'return_on_equity': 1.479},
        '7203.T': {'trailing_pe': 8.9, 'currency': 'JPY'}
    }
```

## 🏗️ Test Configuration Files

### Test-Specific Configs
- `tests/test_configs/basic_test.yaml` - Unit testing
- `tests/test_configs/international_test.yaml` - International markets

### Usage in Tests
```python
config = load_analysis_config('tests/test_configs/basic_test.yaml')
pipeline = AnalysisPipeline(config)
results = pipeline.run_analysis()
```

## 🚨 Error Handling Tests

### Network Errors
- Yahoo Finance API failures
- Timeout handling
- Partial data scenarios

### Configuration Errors
- Invalid YAML syntax
- Missing required fields
- Unrealistic thresholds

### Data Quality Issues
- Missing financial metrics
- Currency conversion errors
- Market holiday handling

## 📈 Performance Testing

### Benchmarks
- Small universe (5 stocks): < 5 seconds
- Medium universe (50 stocks): < 30 seconds  
- Large universe (500 stocks): < 300 seconds

### Memory Usage
- Monitors memory consumption during analysis
- Tests with large stock universes
- Garbage collection validation

## 🔄 CI/CD Integration

### GitHub Actions
- **Multi-Python versions**: 3.8, 3.9, 3.10, 3.11
- **Automated testing**: On push and PR
- **Coverage reporting**: Codecov integration
- **Security scanning**: Bandit integration

### Workflow Steps
1. Code linting with Ruff
2. Unit test execution
3. Integration testing
4. Configuration validation
5. Documentation build
6. Security scanning
7. Performance benchmarking

## 📋 Test Checklist

Before committing code, ensure:

- [ ] All tests pass locally
- [ ] Coverage remains above 80%
- [ ] New features have corresponding tests
- [ ] International functionality tested
- [ ] Documentation updated
- [ ] No security issues detected

## 🛠️ Writing New Tests

### Test Structure
```python
class TestNewFeature:
    """Test new feature functionality."""
    
    @pytest.fixture
    def test_data(self):
        return {...}
    
    def test_basic_functionality(self, test_data):
        # Arrange
        input_data = test_data
        
        # Act  
        result = my_function(input_data)
        
        # Assert
        assert result is not None
        assert result['expected_field'] == expected_value
```

### Best Practices
- Use descriptive test names
- Follow Arrange-Act-Assert pattern
- Mock external dependencies  
- Test both success and failure cases
- Include edge cases and boundary conditions

### Markers
Add appropriate markers to new tests:
```python
@pytest.mark.unit
@pytest.mark.international
@pytest.mark.slow
def test_my_feature():
    pass
```

## 🐛 Debugging Tests

### Verbose Output
```bash
# Detailed test output
uv run pytest -v -s

# Show local variables on failure
uv run pytest --tb=long

# Debug specific test
uv run pytest tests/test_file.py::TestClass::test_method -v -s
```

### Common Issues
1. **Mock not working**: Check import paths and side_effects
2. **Fixture not found**: Ensure fixture is in conftest.py or imported
3. **Coverage too low**: Add tests for uncovered lines
4. **Slow tests**: Use smaller datasets or mark as slow

## 📚 Resources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-cov documentation](https://pytest-cov.readthedocs.io/)
- [Mock library guide](https://docs.python.org/3/library/unittest.mock.html)
- [Coverage.py documentation](https://coverage.readthedocs.io/)

---

## 🎯 Test Goals

The test suite ensures:
- **Reliability**: All components work as expected
- **International Support**: Global markets function correctly  
- **Valuation Accuracy**: Models produce reasonable results
- **Error Resilience**: Graceful handling of edge cases
- **Performance**: Acceptable speed for large datasets
- **Security**: No vulnerabilities in analysis code

**Happy Testing! 🧪✨**