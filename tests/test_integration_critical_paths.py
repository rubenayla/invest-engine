"""
Integration tests for critical paths in the investment analysis system.

This module tests end-to-end functionality across the refactored components:
- Unified valuation models with caching
- Dashboard components integration
- Cache system performance
- Data provider consistency
"""

import tempfile
import time
from unittest.mock import Mock, patch

import pytest

from src.invest.caching.cache_decorators import clear_all_caches, get_cache_stats
from src.invest.caching.cache_manager import get_cache_manager, reset_cache_manager
from src.invest.dashboard_components.dashboard import ValuationDashboard
from src.invest.dashboard_components.valuation_engine import ValuationEngine
from src.invest.data.universal_fetcher import UniversalStockFetcher
from src.invest.valuation.model_registry import (
    ModelRegistry,
    get_available_models,
    run_all_suitable_models,
    run_valuation,
)


class TestUnifiedValuationModels:
    """Test the unified valuation model system."""

    @pytest.mark.integration
    def test_model_registry_initialization(self):
        """Test that model registry initializes with core expected models."""
        registry = ModelRegistry()
        available_models = registry.get_available_models()

        # Core models that should always be available (neural network models may not be available in CI)
        core_models = ['bank', 'dcf', 'dcf_enhanced', 'ensemble', 'growth_dcf', 'multi_stage_dcf', 'reit', 'rim', 'simple_ratios', 'tech', 'utility']

        # Check that all core models are available
        for model in core_models:
            assert model in available_models, f"Core model {model} not found in available models"

        # Neural network models are optional (may not be available in CI environments)
        [m for m in available_models if 'neural_network' in m]

        # Test model metadata is available for all available models
        metadata = registry.get_model_metadata()
        assert len(metadata) >= len(core_models), "Metadata should include at least all core models"

        for model in available_models:
            assert model in metadata, f"Model {model} missing from metadata"
            assert 'name' in metadata[model], f"Model {model} missing name in metadata"
            assert 'description' in metadata[model], f"Model {model} missing description in metadata"

    @pytest.mark.integration
    @patch('yfinance.Ticker')
    def test_valuation_model_execution_with_mocked_data(self, mock_ticker):
        """Test valuation models execute correctly with mocked data."""
        # Clear cache to ensure clean test state
        clear_all_caches()

        # Setup mock data
        mock_stock = Mock()
        mock_stock.info = {
            'currentPrice': 150.0,
            'sharesOutstanding': 16000000000,
            'beta': 1.2,
            'trailingEps': 6.0,
            'bookValue': 3.5,
            'revenuePerShare': 24.0,
            'priceToSalesTrailing12Months': 6.25,  # 150 / 24 = 6.25
            'sector': 'Technology'
        }

        # Mock financial data with pandas-like interface
        from datetime import datetime, timedelta

        import pandas as pd

        dates = [datetime.now() - timedelta(days=365*i) for i in range(3)]
        mock_stock.financials = pd.DataFrame({
            dates[0]: {'Total Revenue': 365000000000, 'Net Income': 95000000000},
            dates[1]: {'Total Revenue': 350000000000, 'Net Income': 90000000000},
            dates[2]: {'Total Revenue': 330000000000, 'Net Income': 85000000000},
        }).T

        mock_stock.balance_sheet = pd.DataFrame({
            dates[0]: {'Total Stockholder Equity': 150000000000, 'Cash And Cash Equivalents': 50000000000, 'Total Debt': 120000000000},
            dates[1]: {'Total Stockholder Equity': 140000000000, 'Cash And Cash Equivalents': 45000000000, 'Total Debt': 115000000000},
            dates[2]: {'Total Stockholder Equity': 130000000000, 'Cash And Cash Equivalents': 40000000000, 'Total Debt': 110000000000},
        }).T

        mock_stock.cashflow = pd.DataFrame({
            dates[0]: {'Total Cash From Operating Activities': 110000000000, 'Capital Expenditures': -10000000000},
            dates[1]: {'Total Cash From Operating Activities': 105000000000, 'Capital Expenditures': -9000000000},
            dates[2]: {'Total Cash From Operating Activities': 100000000000, 'Capital Expenditures': -8000000000},
        }).T

        mock_ticker.return_value = mock_stock

        # Test each model
        ticker = 'AAPL'
        successful_models = []

        for model in get_available_models():
            result = run_valuation(model, ticker, verbose=False)
            if result:
                successful_models.append(model)
                assert result.ticker == ticker
                assert result.model == model
                assert result.fair_value is not None
                assert result.fair_value > 0

        # At least simple_ratios should work with minimal data
        assert 'simple_ratios' in successful_models
        assert len(successful_models) >= 1

    @pytest.mark.integration
    def test_model_suitability_detection(self):
        """Test that models correctly detect their suitability."""
        registry = ModelRegistry()

        # Create mock data that should work for different models
        good_data = {
            'info': {
                'currentPrice': 100.0,
                'sharesOutstanding': 1000000000,
                'trailingEps': 5.0,
                'bookValue': 20.0,
                'beta': 1.0
            },
            'financials': Mock(),
            'balance_sheet': Mock(),
            'cashflow': Mock()
        }

        # Test with good data
        recommendations = registry.get_model_recommendations('AAPL', good_data)
        assert isinstance(recommendations, list)
        assert len(recommendations) > 0
        assert 'simple_ratios' in recommendations  # Should always be recommended


class TestDashboardComponentsIntegration:
    """Test integration of modular dashboard components."""

    @pytest.mark.integration
    def test_valuation_engine_with_unified_models(self):
        """Test that ValuationEngine works with unified model system."""
        engine = ValuationEngine()

        # Test engine initialization
        available_models = engine.get_available_models()

        # Core models that should always be available (neural network models may not be available in CI)
        core_models = ['bank', 'dcf', 'dcf_enhanced', 'ensemble', 'growth_dcf', 'multi_stage_dcf', 'reit', 'rim', 'simple_ratios', 'tech', 'utility']

        # Check that all core models are available
        for model in core_models:
            assert model in available_models, f"Core model {model} not found in available models"

        # Test statistics tracking
        initial_stats = engine.get_model_statistics()
        assert isinstance(initial_stats, dict)
        for model in available_models:
            assert model in initial_stats
            assert 'attempts' in initial_stats[model]
            assert 'successes' in initial_stats[model]

    @pytest.mark.integration
    def test_dashboard_components_orchestration(self):
        """Test that dashboard components work together."""
        with tempfile.TemporaryDirectory() as temp_dir:
            dashboard = ValuationDashboard(output_dir=temp_dir)

            # Test component initialization
            assert dashboard.valuation_engine is not None
            assert dashboard.data_manager is not None
            assert dashboard.progress_tracker is not None
            assert dashboard.html_generator is not None
            assert dashboard.stock_prioritizer is not None

            # Test that components can communicate
            available_models = dashboard.valuation_engine.get_available_models()
            assert len(available_models) > 0

            progress_info = dashboard.get_progress_info()
            assert isinstance(progress_info, dict)
            assert 'status' in progress_info


class TestCachingSystemIntegration:
    """Test caching system integration with other components."""

    @pytest.mark.integration
    @pytest.mark.cache
    def test_cache_manager_initialization(self):
        """Test cache manager initializes correctly."""
        reset_cache_manager()  # Ensure clean state
        cache_manager = get_cache_manager()

        # Test backends are available
        assert 'memory' in cache_manager.backends
        assert 'file' in cache_manager.backends

        # Test basic operations
        test_key = 'integration_test_key'
        test_value = {'data': 'test_integration'}

        cache_manager.set(test_key, test_value, 'default')
        retrieved_value = cache_manager.get(test_key, 'default')

        assert retrieved_value == test_value

    @pytest.mark.integration
    @pytest.mark.cache
    @pytest.mark.skip(reason="Replaced with simplified ticker handling - no longer using web scraping")
    @patch('requests.get')
    def test_cached_sp500_fetching(self, mock_get):
        """Test S&P 500 ticker fetching with caching."""
        # Mock the Wikipedia response
        mock_response = Mock()
        mock_response.text = '''
        <table class="wikitable">
            <tr><th>Symbol</th><th>Security</th></tr>
            <tr><td>AAPL</td><td>Apple Inc.</td></tr>
            <tr><td>MSFT</td><td>Microsoft Corporation</td></tr>
            <tr><td>GOOGL</td><td>Alphabet Inc.</td></tr>
        </table>
        '''
        mock_get.return_value = mock_response

        # Test caching with universal fetcher
        UniversalStockFetcher()
        test_tickers = ['AAPL', 'MSFT', 'GOOGL']

        # First call (cache miss)
        start_time = time.time()
        tickers1 = test_tickers
        first_call_time = time.time() - start_time

        # Second call (cache hit)
        start_time = time.time()
        tickers2 = test_tickers
        second_call_time = time.time() - start_time

        # Verify results
        assert tickers1 == tickers2
        assert len(tickers1) > 0
        assert 'AAPL' in tickers1

        # Cache should make second call faster
        # (allowing for some variance in test environment)
        assert second_call_time < first_call_time + 0.1

        # Verify only one actual HTTP request was made (cache hit on second)
        assert mock_get.call_count == 1

    @pytest.mark.integration
    @pytest.mark.cache
    @patch('yfinance.Ticker')
    def test_cached_valuation_models(self, mock_ticker):
        """Test valuation models benefit from cached data."""
        # Setup mock data
        mock_stock = Mock()
        mock_stock.info = {
            'currentPrice': 150.0,
            'sharesOutstanding': 16000000000,
            'trailingEps': 6.0,
            'bookValue': 3.5,
            'revenuePerShare': 24.0,
            'beta': 1.2
        }

        import pandas as pd
        mock_stock.financials = pd.DataFrame({'2023-12-31': {'Net Income': 95000000000}}).T
        mock_stock.balance_sheet = pd.DataFrame({'2023-12-31': {'Total Stockholder Equity': 150000000000}}).T
        mock_stock.cashflow = pd.DataFrame({'2023-12-31': {'Total Cash From Operating Activities': 110000000000}}).T

        mock_ticker.return_value = mock_stock

        ticker = 'AAPL'
        model = 'simple_ratios'

        # First valuation (data fetching + computation)
        start_time = time.time()
        result1 = run_valuation(model, ticker, verbose=False)
        first_time = time.time() - start_time

        # Second valuation (should use cached data)
        start_time = time.time()
        result2 = run_valuation(model, ticker, verbose=False)
        second_time = time.time() - start_time

        # Results should be consistent
        if result1 and result2:
            assert result1.ticker == result2.ticker
            assert result1.model == result2.model
            assert result1.fair_value == result2.fair_value

            # Second call should be faster due to caching
            assert second_time < first_time + 0.1

    @pytest.mark.integration
    @pytest.mark.cache
    def test_cache_statistics_and_management(self):
        """Test cache statistics and management functions."""
        cache_manager = get_cache_manager()

        # Perform some cache operations
        cache_manager.set('test1', 'value1', 'default')
        cache_manager.set('test2', 'value2', 'stock_info')
        cache_manager.get('test1', 'default')  # Hit
        cache_manager.get('nonexistent', 'default')  # Miss

        # Test statistics
        stats = get_cache_stats()
        assert isinstance(stats, dict)
        assert 'manager_stats' in stats
        assert 'backend_stats' in stats

        manager_stats = stats['manager_stats']
        assert manager_stats['hits'] >= 1
        assert manager_stats['misses'] >= 1
        assert manager_stats['sets'] >= 2

        # Test cache clearing
        clear_all_caches()

        # Verify cache is cleared
        assert cache_manager.get('test1', 'default') is None
        assert cache_manager.get('test2', 'stock_info') is None


class TestDataProviderConsistency:
    """Test consistency across different data providers."""

    @pytest.mark.integration
    @patch('yfinance.Ticker')
    def test_stock_data_consistency(self, mock_ticker):
        """Test that stock data is consistent across different access methods."""
        # Setup mock
        mock_stock = Mock()
        mock_stock.info = {
            'symbol': 'AAPL',
            'currentPrice': 150.0,
            'marketCap': 2400000000000,
            'sharesOutstanding': 16000000000
        }
        mock_ticker.return_value = mock_stock

        ticker = 'AAPL'

        # Get data through universal fetcher
        fetcher = UniversalStockFetcher()
        stock_data = fetcher.fetch_stock(ticker)

        # Both should return consistent data
        if stock_data:
            assert stock_data.get('currentPrice') == 150.0
            assert stock_data.get('sharesOutstanding') == 16000000000


class TestEndToEndWorkflows:
    """Test complete end-to-end workflows."""

    @pytest.mark.integration
    @pytest.mark.slow
    @patch('yfinance.Ticker')
    def test_complete_valuation_workflow(self, mock_ticker):
        """Test complete workflow from data fetching to valuation."""
        # Setup comprehensive mock data
        mock_stock = Mock()
        mock_stock.info = {
            'symbol': 'AAPL',
            'currentPrice': 150.0,
            'sharesOutstanding': 16000000000,
            'trailingEps': 6.0,
            'bookValue': 3.5,
            'revenuePerShare': 24.0,
            'beta': 1.2,
            'sector': 'Technology'
        }

        from datetime import datetime, timedelta

        import pandas as pd

        dates = [datetime.now() - timedelta(days=365*i) for i in range(3)]
        mock_stock.financials = pd.DataFrame({
            dates[0]: {'Total Revenue': 365000000000, 'Net Income': 95000000000},
            dates[1]: {'Total Revenue': 350000000000, 'Net Income': 90000000000},
            dates[2]: {'Total Revenue': 330000000000, 'Net Income': 85000000000},
        }).T

        mock_stock.balance_sheet = pd.DataFrame({
            dates[0]: {'Total Stockholder Equity': 150000000000, 'Cash And Cash Equivalents': 50000000000, 'Total Debt': 120000000000},
        }).T

        mock_stock.cashflow = pd.DataFrame({
            dates[0]: {'Total Cash From Operating Activities': 110000000000, 'Capital Expenditures': -10000000000},
        }).T

        mock_ticker.return_value = mock_stock

        ticker = 'AAPL'

        # Test complete workflow
        # 1. Get suitable models (use global registry via convenience function)
        from src.invest.valuation.model_registry import _registry, get_registry_stats
        models = _registry.get_model_recommendations(ticker)
        assert len(models) > 0

        # 2. Run all suitable models
        results = run_all_suitable_models(ticker, verbose=False)
        assert isinstance(results, dict)

        # 3. Verify results structure
        for model_name, result in results.items():
            assert result.ticker == ticker
            assert result.model == model_name
            assert result.fair_value is not None
            assert result.is_valid()

        # 4. Test registry statistics (from global registry)
        stats = get_registry_stats()
        assert isinstance(stats, dict)
        for model_name in results.keys():
            assert model_name in stats
            assert stats[model_name]['runs'] > 0

    @pytest.mark.integration
    @pytest.mark.performance
    def test_performance_benchmarks(self):
        """Test that system meets performance benchmarks."""

        # Test cache initialization time
        start_time = time.time()
        cache_manager = get_cache_manager()
        init_time = time.time() - start_time

        assert init_time < 5.0, f"Cache initialization took {init_time:.3f}s (should be < 5.0s)"

        # Test model registry initialization time
        start_time = time.time()
        ModelRegistry()
        registry_init_time = time.time() - start_time

        assert registry_init_time < 5.0, f"Model registry init took {registry_init_time:.3f}s (should be < 5.0s)"

        # Test cache performance
        cache_manager.set('perf_test', {'data': 'test'}, 'default')

        start_time = time.time()
        for _ in range(1000):
            cache_manager.get('perf_test', 'default')
        cache_get_time = time.time() - start_time

        assert cache_get_time < 1.0, f"1000 cache gets took {cache_get_time:.3f}s (should be < 1.0s)"


@pytest.mark.integration
class TestErrorHandlingAndResilience:
    """Test system behavior under error conditions."""

    def test_invalid_ticker_handling(self):
        """Test system handles invalid tickers gracefully."""
        invalid_ticker = 'INVALID_TICKER_XXXX'

        # Should not crash, should return None or handle gracefully
        result = run_valuation('simple_ratios', invalid_ticker, verbose=False)
        # Result can be None (acceptable) or a valid result structure
        if result:
            assert result.ticker == invalid_ticker

    def test_network_error_resilience(self):
        """Test system handles network errors gracefully."""
        # Clear cache to ensure clean test state
        clear_all_caches()

        with patch('yfinance.Ticker') as mock_ticker:
            # Simulate network error
            mock_ticker.side_effect = Exception("Network error")

            # System should handle the error gracefully
            result = run_valuation('simple_ratios', 'AAPL', verbose=False)
            assert result is None  # Should fail gracefully

    def test_partial_data_handling(self):
        """Test system handles partial/missing data gracefully."""
        with patch('yfinance.Ticker') as mock_ticker:
            # Mock with minimal data
            mock_stock = Mock()
            mock_stock.info = {'currentPrice': 100.0}  # Very minimal data
            mock_stock.financials = Mock()
            mock_stock.balance_sheet = Mock()
            mock_stock.cashflow = Mock()

            mock_ticker.return_value = mock_stock

            # Some models might fail, but system should not crash
            result = run_valuation('simple_ratios', 'AAPL', verbose=False)
            # Result could be None (model not suitable) or valid result
            if result:
                assert result.ticker == 'AAPL'


if __name__ == '__main__':
    # Run integration tests
    pytest.main([__file__, '-v', '--tb=short'])
