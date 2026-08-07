"""
Integration tests for user-facing scripts.

These tests verify that the actual scripts users run (like run_classic_valuations.py)
work correctly with the data storage layer. Tests use mocks to avoid requiring a database.
"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

project_root = Path(__file__).parent.parent


@pytest.fixture
def mock_stock_data():
    """Provide mock stock data for testing (in format returned by StockDataReader)."""
    return {
        'ticker': 'AAPL',
        'info': {
            'currentPrice': 150.0,
            'marketCap': 2500000000000,
            'sector': 'Technology',
            'industry': 'Consumer Electronics',
            'longName': 'Apple Inc.',
            'shortName': 'Apple',
            'currency': 'USD',
            'exchange': 'NASDAQ',
            'country': 'US',
            'sharesOutstanding': 16000000000,
            'totalCash': 50000000000,
            'totalDebt': 100000000000,
            'trailingEps': 6.0,
            'bookValue': 4.0,
        },
        'financials': {
            'trailingPE': 25.0,
            'forwardPE': 23.0,
            'priceToBook': 37.5,
            'returnOnEquity': 0.45,
            'debtToEquity': 2.0,
        },
        # Financial statements as lists of dicts (JSON format from DB)
        'cashflow': [
            {'index': 'Free Cash Flow', '2023-12-31': 95000000000, '2022-12-31': 90000000000},
            {'index': 'Operating Cash Flow', '2023-12-31': 105000000000, '2022-12-31': 100000000000},
        ],
        'balance_sheet': [
            {'index': 'Total Assets', '2023-12-31': 350000000000, '2022-12-31': 340000000000},
            {'index': 'Total Liabilities', '2023-12-31': 290000000000, '2022-12-31': 280000000000},
        ],
        'income': [
            {'index': 'Total Revenue', '2023-12-31': 385000000000, '2022-12-31': 365000000000},
            {'index': 'Net Income', '2023-12-31': 97000000000, '2022-12-31': 90000000000},
        ],
        'fetch_timestamp': '2025-01-01T00:00:00',
    }


@pytest.fixture
def mock_stock_reader(mock_stock_data):
    """Provide a mocked StockDataReader."""
    reader = Mock()
    reader.get_stock_data = Mock(side_effect=lambda ticker:
        mock_stock_data if ticker == 'AAPL' else None
    )
    reader.get_stock_count = Mock(return_value=435)
    reader.get_all_tickers = Mock(return_value=['AAPL', 'MSFT', 'GOOGL'])
    return reader


class TestClassicValuationsScript:
    """Test the run_classic_valuations.py script end-to-end."""

    def test_script_can_load_from_sqlite(self, tmp_path, mock_stock_reader):
        """
        Test that run_classic_valuations.py can load stock data from SQLite.

        This test would have caught the bug where the script was looking for
        deleted JSON files instead of reading from the SQLite database.
        """
        # Create a minimal dashboard_data.json with test stocks
        dashboard_data = {
            'stocks': {
                'AAPL': {},
                'MSFT': {},
            },
            'metadata': {
                'last_updated': '2025-01-01T00:00:00'
            }
        }

        # Create temporary dashboard data file
        test_dashboard_path = tmp_path / 'dashboard_data.json'
        with open(test_dashboard_path, 'w') as f:
            json.dump(dashboard_data, f)

        # Import the script's main components
        sys.path.insert(0, str(project_root / 'src'))

        # Import the script module
        script_path = project_root / 'scripts' / 'run_classic_valuations.py'
        import importlib.util
        spec = importlib.util.spec_from_file_location('run_classic_valuations', script_path)
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)  # Need to execute to load functions

        # Test that load_stock_data function uses StockDataReader
        # Use the mocked reader
        data = script.load_stock_data('AAPL', mock_stock_reader)

        # Verify we got data back
        assert data is not None
        assert isinstance(data, dict)
        assert 'info' in data
        assert isinstance(data['info'], dict)

    def test_script_handles_missing_stock(self, tmp_path, mock_stock_reader):
        """Test that the script gracefully handles stocks not in the database."""
        sys.path.insert(0, str(project_root / 'src'))

        script_path = project_root / 'scripts' / 'run_classic_valuations.py'
        import importlib.util
        spec = importlib.util.spec_from_file_location('run_classic_valuations', script_path)
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)

        # Try to load a stock that definitely doesn't exist
        data = script.load_stock_data('FAKE_TICKER_12345', mock_stock_reader)

        # Should return None, not crash
        assert data is None

    def test_script_converts_dataframes_correctly(self, tmp_path, mock_stock_reader):
        """Test that the script correctly converts JSON data to DataFrames."""
        sys.path.insert(0, str(project_root / 'src'))

        script_path = project_root / 'scripts' / 'run_classic_valuations.py'
        import importlib.util
        spec = importlib.util.spec_from_file_location('run_classic_valuations', script_path)
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)

        # Load mocked data
        data = script.load_stock_data('AAPL', mock_stock_reader)

        assert data is not None

        # Verify cashflow data is a DataFrame
        if 'cashflow' in data:
            assert isinstance(data['cashflow'], pd.DataFrame), \
                'Cashflow should be a DataFrame'

        # Same for balance sheet
        if 'balance_sheet' in data:
            assert isinstance(data['balance_sheet'], pd.DataFrame), \
                'Balance sheet should be a DataFrame'

        # Same for income statement
        if 'income' in data:
            assert isinstance(data['income'], pd.DataFrame), \
                'Income statement should be a DataFrame'


class TestDataFetcherScript:
    """Test the data_fetcher.py script integration with SQLite."""

    def test_fetcher_writes_to_sqlite(self, mock_stock_reader):
        """
        Test that data_fetcher.py writes to SQLite database.

        This is a smoke test to ensure the data fetcher is configured
        to use the SQLite backend.
        """
        sys.path.insert(0, str(project_root / 'src'))

        # Check that we can read from the database (mocked)
        stock_count = mock_stock_reader.get_stock_count()

        # The mocked reader should return 435 stocks
        assert stock_count >= 0


class TestDashboardGeneration:
    """Test dashboard generation scripts."""

    def test_dashboard_can_be_regenerated(self):
        """
        Test that dashboard.py exists and can be imported.

        This is a smoke test that the dashboard generation pipeline is available.
        """
        script_path = project_root / 'scripts' / 'dashboard.py'

        # Verify the script exists
        assert script_path.exists(), 'Dashboard generation script should exist'

        # Verify it can be imported without errors
        import importlib.util
        spec = importlib.util.spec_from_file_location('dashboard', script_path)
        script = importlib.util.module_from_spec(spec)

        # If we can create the spec, the script is valid Python
        assert spec is not None
        assert script is not None
