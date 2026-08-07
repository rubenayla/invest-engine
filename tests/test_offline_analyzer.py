"""Tests for offline analyzer functionality."""

import json
import os
import sys

import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.offline_analyzer import DashboardIntegration, OfflineValuationEngine


@pytest.mark.slow
class TestOfflineValuationEngine:
    """Test the offline valuation analysis engine."""

    def test_engine_initialization(self, tmp_path):
        """Test engine initializes with cache."""
        engine = OfflineValuationEngine(cache_dir=str(tmp_path))
        assert engine.cache is not None

    def test_calculate_composite_score(self, tmp_path):
        """Test composite score calculation."""
        engine = OfflineValuationEngine(cache_dir=str(tmp_path))

        stock_data = {
            'financials': {
                'trailingPE': 15,
                'debtToEquity': 50,
                'returnOnEquity': 0.15,
                'earningsGrowth': 0.10
            }
        }

        score = engine.calculate_composite_score(stock_data)
        assert 0 <= score <= 100
        assert isinstance(score, (int, float))

    def test_analyze_stock_with_complete_data(self, tmp_path):
        """Test analyzing stock with complete data."""
        engine = OfflineValuationEngine(cache_dir=str(tmp_path))

        stock_data = {
            'ticker': 'AAPL',
            'info': {
                'marketCap': 3000000000000,
                'currentPrice': 150.0,
                'sector': 'Technology',
                'longName': 'Apple Inc.'
            },
            'financials': {
                'trailingPE': 25,
                'forwardPE': 22,
                'priceToBook': 40,
                'returnOnEquity': 1.5,
                'debtToEquity': 150,
                'revenueGrowth': 0.05,
                'earningsGrowth': 0.10
            },
            'price_data': {
                'current_price': 150.0,
                'price_52w_high': 180,
                'price_52w_low': 120
            }
        }

        analysis = engine.analyze_stock('AAPL', stock_data)

        assert analysis['ticker'] == 'AAPL'
        assert analysis['status'] == 'completed'
        assert analysis['market_cap'] == 3000000000000
        assert 'valuations' in analysis
        # Check for available models (some may fail due to insufficient data)
        valuations = analysis['valuations']
        assert len(valuations) > 1  # Should have current_price plus at least one model

        # Verify structure of returned models (any that were attempted)
        available_models = [k for k in valuations.keys() if k != 'current_price']
        assert len(available_models) >= 1  # At least one model should be attempted

        # All model results should have consistent structure
        for model_name in available_models:
            model_result = valuations[model_name]
            assert 'fair_value' in model_result
            assert 'confidence' in model_result

    def test_analyze_stock_with_missing_data(self, tmp_path):
        """Test analyzing stock with missing data."""
        engine = OfflineValuationEngine(cache_dir=str(tmp_path))

        stock_data = {
            'ticker': 'XYZ',
            'info': {},
            'financials': {},
            'price_data': {}
        }

        analysis = engine.analyze_stock('XYZ', stock_data)

        assert analysis['ticker'] == 'XYZ'
        assert analysis['status'] == 'completed'
        assert analysis['market_cap'] == 0
        # With missing data, most models should fail gracefully
        valuations = analysis['valuations']
        assert 'current_price' in valuations  # Current price should be available
        # Check that models either returned None or error for missing data
        available_models = [k for k in valuations.keys() if k != 'current_price']
        for model_name in available_models:
            model_result = valuations[model_name]
            # Should either be None or have error information
            if model_result is not None:
                assert 'fair_value' in model_result
                assert 'confidence' in model_result

    def test_multiple_valuation_methods(self, tmp_path):
        """Test all valuation methods are calculated."""
        engine = OfflineValuationEngine(cache_dir=str(tmp_path))

        stock_data = {
            'info': {
                'marketCap': 1000000000,
                'currentPrice': 100.0,
                'sector': 'Technology'
            },
            'financials': {
                'trailingPE': 20,
                'priceToBook': 5,
                'earningsGrowth': 0.15,
                'totalRevenue': 500000000,
                'sharesOutstanding': 10000000
            },
            'price_data': {'current_price': 100.0}
        }

        analysis = engine.analyze_stock('TEST', stock_data)
        valuations = analysis['valuations']

        # Check that multiple valuation methods are attempted
        available_models = [k for k in valuations.keys() if k != 'current_price']
        assert len(available_models) >= 5, f"Expected at least 5 models, got {len(available_models)}: {available_models}"

        # Verify all attempted models have consistent structure
        for model_name in available_models:
            model_result = valuations[model_name]
            if model_result is not None:
                assert 'fair_value' in model_result, f"Model {model_name} missing fair_value"
                assert 'confidence' in model_result, f"Model {model_name} missing confidence"


class TestDashboardIntegration:
    """Test dashboard integration functionality."""

    def test_update_dashboard_data(self, tmp_path):
        """Test updating dashboard with analysis results."""
        integration = DashboardIntegration(dashboard_dir=str(tmp_path))

        analysis_results = {
            'AAPL': {
                'ticker': 'AAPL',
                'status': 'completed',
                'market_cap': 3000000000000,
                'composite_score': 85
            },
            'GOOGL': {
                'ticker': 'GOOGL',
                'status': 'completed',
                'market_cap': 2000000000000,
                'composite_score': 80
            }
        }

        integration.update_dashboard_data(analysis_results)

        # Check dashboard file was created
        dashboard_file = tmp_path / 'dashboard_data.json'
        assert dashboard_file.exists()

        # Verify content
        with open(dashboard_file) as f:
            data = json.load(f)
            assert data['total_stocks'] == 2
            assert data['successful_analyses'] == 2
            assert 'AAPL' in data['stocks']
            assert 'GOOGL' in data['stocks']

    def test_dashboard_summary_in_data(self, tmp_path):
        """Test dashboard data includes summary information."""
        integration = DashboardIntegration(dashboard_dir=str(tmp_path))

        analysis_results = {
            'AAPL': {'composite_score': 85, 'status': 'completed', 'ticker': 'AAPL'},
            'GOOGL': {'composite_score': 80, 'status': 'completed', 'ticker': 'GOOGL'},
            'FAIL': {'status': 'failed', 'ticker': 'FAIL'}
        }

        integration.update_dashboard_data(analysis_results)

        # Read the saved dashboard data
        dashboard_file = tmp_path / 'dashboard_data.json'
        with open(dashboard_file) as f:
            data = json.load(f)

        # Check summary fields in dashboard data
        assert data['total_stocks'] == 3
        assert data['successful_analyses'] == 2
        assert 'last_updated' in data
        assert data['analysis_method'] == 'offline_cached'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
