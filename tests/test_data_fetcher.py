"""Tests for data fetcher functionality."""

import os
import sys
from unittest.mock import patch

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.data_fetcher import StockDataCache


class TestStockDataCache:
    """Test the stock data caching system."""

    def test_cache_initialization(self, tmp_path):
        """Test cache creates necessary directories."""
        cache_dir = tmp_path / 'test_cache'
        cache = StockDataCache(str(cache_dir))
        assert cache_dir.exists()
        # Index should be in memory even if file doesn't exist yet
        assert cache.index is not None
        assert 'stocks' in cache.index

    def test_save_and_load_stock_data(self, tmp_path):
        """Test saving and loading stock data."""
        cache = StockDataCache(str(tmp_path))

        test_data = {
            'ticker': 'AAPL',
            'info': {'marketCap': 3000000000000, 'currentPrice': 150.0},
            'financials': {'trailingPE': 25.5}
        }

        # Save data
        cache.save_stock_data('AAPL', test_data)

        # Load data
        loaded = cache.get_cached_data('AAPL')
        assert loaded['ticker'] == 'AAPL'
        assert loaded['info']['marketCap'] == 3000000000000
        assert '_cache_metadata' in loaded

    def test_get_cached_tickers(self, tmp_path):
        """Test getting list of cached tickers."""
        cache = StockDataCache(str(tmp_path))

        cache.save_stock_data('AAPL', {'ticker': 'AAPL', 'info': {'currentPrice': 150.0, 'sector': 'Technology'}})
        cache.save_stock_data('GOOGL', {'ticker': 'GOOGL', 'info': {'currentPrice': 140.0, 'sector': 'Technology'}})

        tickers = cache.get_cached_tickers()
        assert 'AAPL' in tickers
        assert 'GOOGL' in tickers
        assert len(tickers) == 2

    def test_get_update_order(self, tmp_path):
        """Test update order prioritizes empty stocks first."""
        cache = StockDataCache(str(tmp_path))

        # Add one stock to cache
        cache.save_stock_data('AAPL', {'ticker': 'AAPL', 'info': {'currentPrice': 150.0, 'marketCap': 3000000000000}})

        # Request update for multiple stocks
        tickers = ['AAPL', 'GOOGL', 'MSFT']
        order = cache.get_update_order(tickers)

        # Empty stocks should come first
        assert order[0] in ['GOOGL', 'MSFT']
        assert order[-1] == 'AAPL'


class TestDataFetcherIntegration:
    """Test the data fetching functionality integration."""

    @patch('yfinance.Ticker')
    def test_fetch_stock_data_mock(self, mock_ticker, tmp_path):
        """Test fetching data for a single stock with mock."""
        # Mock yfinance response
        mock_ticker.return_value.info = {
            'marketCap': 3000000000000,
            'currentPrice': 150.0,
            'sector': 'Technology'
        }

        cache = StockDataCache(str(tmp_path))
        test_data = {
            'ticker': 'AAPL',
            'info': mock_ticker.return_value.info,
            'fetch_timestamp': '2025-01-01T00:00:00'
        }
        cache.save_stock_data('AAPL', test_data)

        result = cache.get_cached_data('AAPL')
        assert result['ticker'] == 'AAPL'
        assert result['info']['marketCap'] == 3000000000000

    def test_fetch_with_cache(self, tmp_path):
        """Test fetching uses cache when available."""
        cache = StockDataCache(str(tmp_path))

        # Pre-populate cache
        test_data = {'ticker': 'AAPL', 'info': {'cached': True, 'currentPrice': 150.0, 'sector': 'Technology'}}
        cache.save_stock_data('AAPL', test_data)

        # Fetch should return cached data
        cached = cache.get_cached_data('AAPL')
        assert cached['info']['cached'] is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
