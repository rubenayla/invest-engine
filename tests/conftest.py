"""
Pytest configuration and shared fixtures for the investment analysis testing suite.
"""
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def pytest_collection_modifyitems(config, items):
    """
    Automatically skip tests that require missing resources.

    This hook checks if required models/data exist and marks tests
    for skipping if resources are missing.
    """
    project_root = Path(__file__).parent.parent

    # Check for trained models
    gbm_models_exist = any([
        (project_root / 'models/neural_network/training/gbm_model_1y.txt').exists(),
        (project_root / 'models/neural_network/training/gbm_model_3y.txt').exists(),
        (project_root / 'models/neural_network/training/gbm_lite_model_1y.txt').exists(),
        (project_root / 'models/neural_network/training/gbm_opportunistic_model_1y.txt').exists(),
    ])

    nn_models_exist = (project_root / 'models/neural_network/training/best_model.pt').exists()
    models_exist = gbm_models_exist or nn_models_exist

    # Check for PostgreSQL database connectivity
    try:
        from invest.data.db import get_connection
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM fundamental_history")
        history_count = cursor.fetchone()[0]
        conn.close()
        has_historical_data = history_count > 1000
    except Exception:
        has_historical_data = False

    # Build skip reasons
    skip_models = pytest.mark.skip(
        reason="Trained models not found. Train models first with scripts in models/neural_network/training/"
    )
    skip_data = pytest.mark.skip(
        reason="Historical data not found. Run: uv run python scripts/populate_fundamental_history.py"
    )

    # Apply skip markers
    for item in items:
        if "requires_models" in item.keywords:
            if not models_exist:
                item.add_marker(skip_models)

        if "requires_data" in item.keywords:
            if not has_historical_data:
                item.add_marker(skip_data)


@pytest.fixture
def mock_stock_data():
    """Comprehensive mock stock data for testing."""
    return {
        # High-quality US tech stock
        "AAPL": {
            "ticker": "AAPL",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "market_cap": 3000000000000,
            "enterprise_value": 2950000000000,
            "current_price": 193.6,
            "trailing_pe": 28.5,
            "forward_pe": 25.8,
            "price_to_book": 40.0,
            "ev_to_ebitda": 22.5,
            "ev_to_revenue": 7.2,
            "return_on_equity": 1.479,
            "return_on_assets": 0.274,
            "debt_to_equity": 195.6,
            "current_ratio": 1.038,
            "revenue_growth": 0.081,
            "earnings_growth": 0.120,
            "target_high_price": 220.0,
            "target_low_price": 160.0,
            "target_mean_price": 190.0,
            "country": "USA",
            "currency": "USD",
            "exchange": "NASDAQ",
        },
        # Value stock example
        "VALUE_STOCK": {
            "ticker": "VALUE_STOCK",
            "sector": "Industrials",
            "industry": "Industrial Machinery",
            "market_cap": 50000000000,
            "enterprise_value": 52000000000,
            "current_price": 45.0,
            "trailing_pe": 12.5,
            "forward_pe": 11.2,
            "price_to_book": 1.8,
            "ev_to_ebitda": 8.5,
            "ev_to_revenue": 1.2,
            "return_on_equity": 0.18,
            "return_on_assets": 0.12,
            "debt_to_equity": 35.0,  # 35% as percentage
            "current_ratio": 2.2,
            "revenue_growth": 0.065,
            "earnings_growth": 0.080,
            "free_cash_flow": 4000000000,
            "shares_outstanding": 1111111111,  # market_cap / current_price
            "target_high_price": 55.0,
            "target_low_price": 40.0,
            "target_mean_price": 47.5,
            "country": "USA",
            "currency": "USD",
            "exchange": "NYSE",
        },
        # Poor quality stock
        "POOR_QUALITY": {
            "ticker": "POOR_QUALITY",
            "sector": "Energy",
            "industry": "Oil & Gas",
            "market_cap": 5000000000,
            "enterprise_value": 8000000000,
            "current_price": 25.0,
            "trailing_pe": 45.0,
            "forward_pe": None,
            "price_to_book": 8.5,
            "ev_to_ebitda": 35.0,
            "ev_to_revenue": 2.8,
            "return_on_equity": 0.05,
            "return_on_assets": 0.02,
            "debt_to_equity": 250.0,  # 250% as percentage (high debt)
            "current_ratio": 0.8,
            "revenue_growth": -0.10,
            "earnings_growth": -0.15,
            "free_cash_flow": 200000000,
            "shares_outstanding": 200000000,  # market_cap / current_price
            "target_high_price": 30.0,
            "target_low_price": 15.0,
            "target_mean_price": 22.0,
            "country": "USA",
            "currency": "USD",
            "exchange": "NYSE",
        },
        # Japanese stock (Toyota)
        "7203.T": {
            "ticker": "7203.T",
            "sector": "Consumer Cyclical",
            "industry": "Auto Manufacturers",
            "market_cap": 37835960000000,
            "enterprise_value": 39000000000000,
            "current_price": 2903.0,
            "trailing_pe": 8.9,
            "forward_pe": 8.2,
            "price_to_book": 1.05,
            "ev_to_ebitda": 6.8,
            "ev_to_revenue": 1.1,
            "return_on_equity": 0.117,
            "return_on_assets": 0.058,
            "debt_to_equity": 103.9,
            "current_ratio": 1.2,
            "revenue_growth": 0.035,
            "earnings_growth": 0.040,
            "target_high_price": 3200.0,
            "target_low_price": 2600.0,
            "target_mean_price": 2900.0,
            "country": "Japan",
            "currency": "JPY",
            "financial_currency": "JPY",
            "exchange": "Tokyo Stock Exchange",
        },
        # Japanese tech stock (Sony)
        "6758.T": {
            "ticker": "6758.T",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "market_cap": 25068590000000,
            "enterprise_value": 24500000000000,
            "current_price": 4183.0,
            "trailing_pe": 21.3,
            "forward_pe": 18.5,
            "price_to_book": 3.03,
            "ev_to_ebitda": 15.2,
            "ev_to_revenue": 2.8,
            "return_on_equity": 0.144,
            "return_on_assets": 0.082,
            "debt_to_equity": 18.8,
            "current_ratio": 1.8,
            "revenue_growth": 0.022,
            "earnings_growth": 0.030,
            "target_high_price": 4800.0,
            "target_low_price": 3800.0,
            "target_mean_price": 4300.0,
            "country": "Japan",
            "currency": "JPY",
            "financial_currency": "JPY",
            "exchange": "Tokyo Stock Exchange",
        },
        # European stock (ASML ADR)
        "ASML": {
            "ticker": "ASML",
            "sector": "Technology",
            "industry": "Semiconductor Equipment",
            "market_cap": 280000000000,
            "enterprise_value": 275000000000,
            "current_price": 680.50,
            "trailing_pe": 35.2,
            "forward_pe": 28.8,
            "price_to_book": 15.8,
            "ev_to_ebitda": 25.5,
            "ev_to_revenue": 12.5,
            "return_on_equity": 0.485,
            "return_on_assets": 0.285,
            "debt_to_equity": 25.3,
            "current_ratio": 2.1,
            "revenue_growth": 0.145,
            "earnings_growth": 0.200,
            "target_high_price": 850.0,
            "target_low_price": 600.0,
            "target_mean_price": 725.0,
            "country": "Netherlands",
            "currency": "EUR",
            "financial_currency": "EUR",
            "exchange": "NASDAQ",  # ADR
        },
    }


@pytest.fixture
def mock_sp500_tickers():
    """Mock S&P 500 ticker list."""
    return [
        "AAPL",
        "MSFT",
        "GOOGL",
        "GOOG",
        "AMZN",
        "TSLA",
        "META",
        "NVDA",
        "BRK-B",
        "UNH",
        "JNJ",
        "XOM",
        "JPM",
        "V",
        "PG",
        "HD",
        "CVX",
        "MA",
        "BAC",
        "ABBV",
        "PFE",
        "AVGO",
        "KO",
        "MRK",
        "PEP",
        "TMO",
        "COST",
        "WMT",
        "CSCO",
        "ACN",
        "VALUE_STOCK",
        "POOR_QUALITY",  # Add test stocks
    ]


@pytest.fixture
def mock_japanese_tickers():
    """Mock Japanese stock ticker list."""
    return [
        "7203.T",  # Toyota
        "6758.T",  # Sony
        "8306.T",  # Mitsubishi UFJ
        "9984.T",  # SoftBank Group
        "6861.T",  # Keyence
        "8316.T",  # Sumitomo Mitsui
        "9432.T",  # NTT
        "4502.T",  # Takeda
        "6501.T",  # Hitachi
        "7974.T",  # Nintendo
    ]


@pytest.fixture
def basic_config():
    """Basic configuration for testing."""
    return {
        "name": "test_config",
        "description": "Basic test configuration",
        "universe": {
            "name": "Test Universe",
            "region": "US",
            "custom_tickers": ["AAPL", "VALUE_STOCK", "POOR_QUALITY"],
            "filters": {
                "min_market_cap_b": 1.0,
                "max_market_cap_b": None,
                "exclude_sectors": [],
                "include_sectors": [],
            },
        },
        "screening": {
            "quality": {
                "min_roe": 0.10,
                "min_roic": 0.08,
                "max_debt_equity": 1.0,
                "min_current_ratio": 1.0,
                "weight": 0.30,
            },
            "value": {
                "max_pe_ratio": 30.0,
                "max_pb_ratio": 5.0,
                "max_ev_ebitda": 20.0,
                "weight": 0.30,
            },
            "growth": {"min_revenue_growth": 0.03, "min_earnings_growth": 0.02, "weight": 0.25},
            "risk": {"max_beta": 1.8, "max_debt_service_ratio": 0.4, "weight": 0.15},
        },
        "valuation": {
            "dcf": {
                "enabled": True,
                "growth_rate": 0.04,
                "discount_rate": 0.10,
                "terminal_multiple": 15.0,
            }
        },
        "output": {"formats": ["txt", "csv", "json"], "top_n": 10, "include_all_stocks": True},
        "max_results": 50,
    }


@pytest.fixture
def international_config():
    """International market configuration for testing."""
    return {
        "name": "international_test",
        "description": "International market test configuration",
        "universe": {
            "name": "Japan Test",
            "market": "japan_topix30",
            "filters": {
                "min_market_cap_b": 5.0,
                "exclude_sectors": [],
            },
        },
        "screening": {
            "quality": {
                "min_roe": 0.08,  # Lower for Japanese market
                "min_roic": 0.06,
                "max_debt_equity": 1.5,  # More tolerant
                "min_current_ratio": 1.0,
                "weight": 0.30,
            },
            "value": {
                "max_pe_ratio": 25.0,  # Adjusted for Japanese market
                "max_pb_ratio": 3.0,
                "max_ev_ebitda": 18.0,
                "weight": 0.35,  # Higher weight on value
            },
            "growth": {
                "min_revenue_growth": 0.02,  # Lower growth expectations
                "min_earnings_growth": 0.01,
                "weight": 0.20,  # Lower weight on growth
            },
            "risk": {"max_beta": 1.6, "max_debt_service_ratio": 0.4, "weight": 0.15},
        },
        "valuation": {
            "dcf": {
                "enabled": True,
                "growth_rate": 0.03,  # Lower growth for Japan
                "discount_rate": 0.09,  # Lower discount rate
                "terminal_multiple": 12.0,  # Conservative terminal multiple
            }
        },
    }


@pytest.fixture
def temp_config_file(basic_config):
    """Create a temporary configuration file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(basic_config, f)
        return f.name


@pytest.fixture
def mock_yfinance():
    """Mock yfinance for consistent testing."""
    with patch("yfinance.Ticker") as mock_ticker:

        def create_mock_stock(ticker_data):
            mock_stock = Mock()
            mock_stock.info = ticker_data
            mock_stock.financials = Mock()
            mock_stock.balance_sheet = Mock()
            mock_stock.cashflow = Mock()
            return mock_stock

        mock_ticker.side_effect = lambda ticker: create_mock_stock(
            mock_stock_data().get(ticker, {})
        )

        yield mock_ticker


@pytest.fixture
def mock_requests():
    """Mock requests for web scraping tests."""
    with patch("requests.get") as mock_get:
        # Mock Wikipedia S&P 500 response
        mock_response = Mock()
        mock_response.text = """
        <table class="wikitable">
            <tr><th>Symbol</th><th>Company</th><th>Sector</th></tr>
            <tr><td>AAPL</td><td>Apple Inc.</td><td>Technology</td></tr>
            <tr><td>MSFT</td><td>Microsoft Corporation</td><td>Technology</td></tr>
            <tr><td>GOOGL</td><td>Alphabet Inc.</td><td>Communication Services</td></tr>
            <tr><td>VALUE_STOCK</td><td>Value Stock Inc.</td><td>Industrials</td></tr>
            <tr><td>POOR_QUALITY</td><td>Poor Quality Corp.</td><td>Energy</td></tr>
        </table>
        """
        mock_get.return_value = mock_response

        yield mock_get


@pytest.fixture(scope="session")
def test_data_dir():
    """Create test data directory."""
    test_dir = Path(__file__).parent / "test_data"
    test_dir.mkdir(exist_ok=True)
    return test_dir


@pytest.fixture
def sample_analysis_results():
    """Sample analysis results for testing."""
    return {
        "config": {"name": "test_analysis"},
        "summary": {"total_analyzed": 3, "passed_filters": 1, "top_score": 85.5, "avg_score": 45.2},
        "stocks": [
            {
                "ticker": "VALUE_STOCK",
                "sector": "Industrials",
                "composite_score": 85.5,
                "quality_score": 90.0,
                "value_score": 95.0,
                "growth_score": 75.0,
                "risk_score": 15.0,
                "passes_filters": True,
                "recommendation": "Buy",
            }
        ],
        "all_stocks": [
            {
                "ticker": "VALUE_STOCK",
                "sector": "Industrials",
                "composite_score": 85.5,
                "quality_score": 90.0,
                "value_score": 95.0,
                "growth_score": 75.0,
                "risk_score": 15.0,
                "passes_filters": True,
            },
            {
                "ticker": "AAPL",
                "sector": "Technology",
                "composite_score": 62.0,
                "quality_score": 75.0,
                "value_score": 25.0,
                "growth_score": 85.0,
                "risk_score": 35.0,
                "passes_filters": False,
            },
            {
                "ticker": "POOR_QUALITY",
                "sector": "Energy",
                "composite_score": 18.0,
                "quality_score": 20.0,
                "value_score": 15.0,
                "growth_score": 10.0,
                "risk_score": 85.0,
                "passes_filters": False,
            },
        ],
        "total_universe": 3,
        "passed_screening": 1,
        "final_results": 1,
    }


@pytest.fixture
def mock_data_providers(mock_stock_data, mock_sp500_tickers, mock_japanese_tickers):
    """Mock all data providers for comprehensive testing."""
    stock_data = mock_stock_data
    sp500_tickers = mock_sp500_tickers
    japanese_tickers = mock_japanese_tickers

    with patch("invest.data.yahoo.get_stock_data") as mock_us_data:
        with patch("invest.data.yahoo.get_sp500_tickers") as mock_sp500:
            with patch("invest.data.international.get_international_stock_data") as mock_intl_data:
                with patch("invest.data.international.get_market_tickers") as mock_market_tickers:
                    mock_us_data.side_effect = lambda ticker: stock_data.get(ticker)
                    mock_sp500.return_value = sp500_tickers
                    mock_intl_data.side_effect = lambda ticker: stock_data.get(ticker)

                    def market_ticker_side_effect(market):
                        if market == "usa_sp500":
                            return sp500_tickers
                        elif market in ["japan_topix30", "japan_major"]:
                            return japanese_tickers
                        else:
                            return ["ASML", "SAP"]

                    mock_market_tickers.side_effect = market_ticker_side_effect

                    yield {
                        "us_data": mock_us_data,
                        "sp500": mock_sp500,
                        "intl_data": mock_intl_data,
                        "market_tickers": mock_market_tickers,
                    }
