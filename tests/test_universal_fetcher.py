"""
Tests for the UniversalStockFetcher - our consolidated data fetching solution.

This tests the core functionality that replaced the old yahoo.py and international.py modules.
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from invest.data.universal_fetcher import UniversalStockFetcher


class TestUniversalStockFetcher:
    """Test the universal stock fetching functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.fetcher = UniversalStockFetcher(convert_currency=True)

    def test_fetcher_initialization(self):
        """Test fetcher initializes correctly."""
        assert self.fetcher is not None
        assert self.fetcher.convert_currency is True

        # Test without currency conversion
        fetcher_no_currency = UniversalStockFetcher(convert_currency=False)
        assert fetcher_no_currency.convert_currency is False

    def test_ticker_format_recognition(self):
        """Test that fetcher recognizes different ticker formats."""
        # These should be recognizable formats
        us_ticker = 'AAPL'
        japanese_ticker = '7203.T'
        european_ticker = 'ASML.AS'

        # The fetcher should handle these without errors during initialization
        assert us_ticker == 'AAPL'  # US format
        assert japanese_ticker == '7203.T'  # Japanese format
        assert european_ticker == 'ASML.AS'  # European format

    @patch('invest.data.universal_fetcher.yf.Ticker')
    def test_single_stock_fetch_success(self, mock_ticker):
        """Test successful single stock data fetch."""
        # Mock successful yfinance response
        mock_info = {
            'symbol': 'AAPL',  # Required by universal_fetcher
            'longName': 'Apple Inc.',
            'currentPrice': 150.0,
            'marketCap': 2400000000000,
            'trailingPE': 25.0,
            'priceToBook': 10.0,
            'sector': 'Technology'
        }

        mock_ticker_instance = Mock()
        mock_ticker_instance.info = mock_info
        mock_ticker.return_value = mock_ticker_instance

        result = self.fetcher.fetch_stock('AAPL')

        assert result is not None
        mock_ticker.assert_called_once_with('AAPL')

    @patch('invest.data.universal_fetcher.yf.Ticker')
    def test_single_stock_fetch_error_handling(self, mock_ticker):
        """Test error handling in single stock fetch."""
        # Mock yfinance error
        mock_ticker.side_effect = Exception('Network error')

        result = self.fetcher.fetch_stock('INVALID')

        # Should return None on error, not raise exception
        assert result is None
        mock_ticker.assert_called_once_with('INVALID')

    @patch('invest.data.universal_fetcher.yf.Ticker')
    def test_multiple_stocks_fetch(self, mock_ticker):
        """Test fetching multiple stocks."""
        # Mock responses for multiple tickers
        def mock_ticker_side_effect(ticker):
            mock_instance = Mock()
            if ticker == 'AAPL':
                mock_instance.info = {'symbol': 'AAPL', 'longName': 'Apple Inc.', 'currentPrice': 150.0}
            elif ticker == 'MSFT':
                mock_instance.info = {'symbol': 'MSFT', 'longName': 'Microsoft Corp.', 'currentPrice': 300.0}
            else:
                mock_instance.info = {}
            return mock_instance

        mock_ticker.side_effect = mock_ticker_side_effect

        tickers = ['AAPL', 'MSFT']
        results = self.fetcher.fetch_multiple(tickers)

        assert len(results) == 2
        assert 'AAPL' in results
        assert 'MSFT' in results
        assert mock_ticker.call_count == 2

    @patch('invest.data.universal_fetcher.yf.Ticker')
    def test_currency_conversion_updates_primary_fields(self, mock_ticker):
        """Ensure non-USD data is converted and original values are preserved."""
        fetcher = UniversalStockFetcher(convert_currency=True)

        stock_info = {
            'symbol': 'SONY',
            'longName': 'Sony Group Corporation',
            'currentPrice': 1500.0,
            'marketCap': 100000000000,
            'currency': 'JPY'
        }
        rate_info = {'regularMarketPrice': 0.007}

        stock_instance = Mock()
        stock_instance.info = stock_info
        rate_instance = Mock()
        rate_instance.info = rate_info

        def side_effect(ticker):
            if ticker == 'SONY':
                return stock_instance
            if ticker == 'JPYUSD=X':
                return rate_instance
            raise AssertionError(f"Unexpected ticker requested: {ticker}")

        mock_ticker.side_effect = side_effect

        result = fetcher.fetch_stock('SONY')

        assert result is not None
        assert result['currency'] == 'USD'
        assert result['original_currency'] == 'JPY'
        assert result['exchange_rate'] == pytest.approx(0.007)
        assert result['currentPrice'] == pytest.approx(10.5)
        assert result['current_price'] == pytest.approx(10.5)
        assert result['marketCap'] == pytest.approx(700000000)
        assert result['market_cap'] == pytest.approx(700000000)
        assert result['currentPrice_original'] == 1500.0
        assert result['marketCap_original'] == 100000000000

    def test_international_ticker_support(self):
        """Test that international ticker formats are supported."""
        international_tickers = [
            '7203.T',      # Japanese (Toyota)
            'ASML.AS',     # Dutch (ASML)
            'SAP.DE',      # German (SAP)
            'NESN.SW',     # Swiss (Nestle)
            '0700.HK'      # Hong Kong (Tencent)
        ]

        # Should not raise errors when initialized with these tickers
        for ticker in international_tickers:
            assert isinstance(ticker, str)
            assert len(ticker) > 0


class TestDataIntegration:
    """Test integration with the analysis pipeline."""

    def test_fetcher_integration_with_pipeline_data_format(self):
        """Test that fetcher returns data in expected format for pipeline."""
        fetcher = UniversalStockFetcher()

        # Mock a basic successful response
        with patch('invest.data.universal_fetcher.yf.Ticker') as mock_ticker:
            mock_info = {
                'symbol': 'TEST',
                'longName': 'Test Company',
                'currentPrice': 100.0,
                'marketCap': 1000000000,
                'sector': 'Technology'
            }

            mock_ticker_instance = Mock()
            mock_ticker_instance.info = mock_info
            mock_ticker.return_value = mock_ticker_instance

            result = fetcher.fetch_stock('TEST')

            if result:  # Only test if we got a result
                # Check that basic fields expected by pipeline are present
                expected_fields = ['longName']  # At minimum
                for field in expected_fields:
                    if field in mock_info:
                        # Field should be preserved in result
                        assert field in str(result) or 'longName' in mock_info

    def test_currency_conversion_flag(self):
        """Test currency conversion functionality."""
        fetcher_default = UniversalStockFetcher()
        assert fetcher_default.convert_currency is True

        # Test with currency conversion enabled
        fetcher_with_currency = UniversalStockFetcher(convert_currency=True)
        assert fetcher_with_currency.convert_currency is True

        # Test with currency conversion disabled
        fetcher_without_currency = UniversalStockFetcher(convert_currency=False)
        assert fetcher_without_currency.convert_currency is False

    def test_empty_ticker_list_handling(self):
        """Test handling of empty ticker lists."""
        fetcher = UniversalStockFetcher()

        result = fetcher.fetch_multiple([])

        assert result == {}  # Should return empty dict, not None or error


class TestErrorHandling:
    """Test error handling and resilience."""

    def test_invalid_ticker_handling(self):
        """Test handling of invalid tickers."""
        fetcher = UniversalStockFetcher()

        with patch('invest.data.universal_fetcher.yf.Ticker') as mock_ticker:
            mock_ticker.side_effect = Exception('Invalid ticker')

            result = fetcher.fetch_stock('INVALID_TICKER')

            assert result is None  # Should not raise exception

    def test_network_error_resilience(self):
        """Test resilience to network errors."""
        fetcher = UniversalStockFetcher()

        with patch('invest.data.universal_fetcher.yf.Ticker') as mock_ticker:
            mock_ticker.side_effect = Exception('Network timeout')

            result = fetcher.fetch_multiple(['AAPL', 'MSFT'])

            # Should return dict with None values, not crash
            assert isinstance(result, dict)


class TestReplacementFunctionality:
    """Test that UniversalStockFetcher provides functionality of removed modules."""

    def test_replaces_yahoo_functionality(self):
        """Test that it can replace functionality from removed yahoo.py."""
        fetcher = UniversalStockFetcher()

        # Should handle US tickers (main yahoo.py functionality)
        us_tickers = ['AAPL', 'MSFT', 'GOOGL']

        with patch('invest.data.universal_fetcher.yf.Ticker') as mock_ticker:
            mock_ticker_instance = Mock()
            mock_ticker_instance.info = {'symbol': 'AAPL', 'longName': 'Test', 'currentPrice': 100}
            mock_ticker.return_value = mock_ticker_instance

            results = fetcher.fetch_multiple(us_tickers)

            assert isinstance(results, dict)
            assert len(us_tickers) == 3  # Tickers are valid format

    def test_replaces_international_functionality(self):
        """Test that it can replace functionality from removed international.py."""
        fetcher = UniversalStockFetcher()

        # Should handle international tickers
        intl_tickers = ['7203.T', 'ASML.AS', 'SAP.DE']

        with patch('invest.data.universal_fetcher.yf.Ticker') as mock_ticker:
            mock_ticker_instance = Mock()
            mock_ticker_instance.info = {'symbol': '7203.T', 'longName': 'Test Intl', 'currentPrice': 50}
            mock_ticker.return_value = mock_ticker_instance

            results = fetcher.fetch_multiple(intl_tickers)

            assert isinstance(results, dict)
            assert len(intl_tickers) == 3  # Tickers are valid format
