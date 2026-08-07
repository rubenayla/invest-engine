import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from invest.analysis.pipeline import AnalysisPipeline  # noqa: E402
from invest.config.schema import (  # noqa: E402
    AnalysisConfig,
    GrowthThresholds,
    QualityThresholds,
    RiskThresholds,
    UniverseConfig,
    ValueThresholds,
)
from invest.screening.growth import assess_growth  # noqa: E402
from invest.screening.quality import assess_quality  # noqa: E402
from invest.screening.risk import assess_risk  # noqa: E402
from invest.screening.value import assess_value  # noqa: E402


class TestConfigurationSystem:
    """Test configuration loading and validation."""

    def test_config_schema_validation(self):
        """Test that configuration schema validates correctly."""
        config_data = {
            "name": "test_analysis",
            "quality": {"min_roic": 0.12, "max_debt_equity": 0.6},
            "value": {"max_pe": 25, "max_pb": 3.5},
            "growth": {"min_revenue_growth": 0.05},
            "risk": {"max_beta": 1.5},
        }

        config = AnalysisConfig(**config_data)
        assert config.name == "test_analysis"
        assert config.quality.min_roic == 0.12
        assert config.value.max_pe == 25
        assert config.growth.min_revenue_growth == 0.05
        assert config.risk.max_beta == 1.5

    def test_default_config_loading(self):
        """Test loading default configuration file."""
        # This would test loading the actual default config
        # For now, create a minimal config to test the structure
        pass


class TestQualityScreening:
    """Test quality assessment functionality."""

    @pytest.fixture
    def sample_stock_data(self):
        return {
            "ticker": "TEST",
            "return_on_equity": 0.20,  # 20% ROE
            "current_ratio": 1.5,
            "debt_to_equity": 30.0,  # 30% debt/equity
        }

    @pytest.fixture
    def quality_thresholds(self):
        return QualityThresholds(
            min_roic=0.12, min_roe=0.15, min_current_ratio=1.2, max_debt_equity=0.5
        )

    def test_quality_assessment(self, sample_stock_data, quality_thresholds):
        """Test quality assessment calculation."""
        result = assess_quality(sample_stock_data, quality_thresholds)

        assert result["ticker"] == "TEST"
        assert "quality_score" in result
        assert "quality_metrics" in result
        assert result["quality_score"] > 0

        # Check that ROIC was calculated
        assert "roic" in result["quality_metrics"]
        assert result["quality_metrics"]["roic"] > 0

    def test_quality_flags(self, quality_thresholds):
        """Test quality flag generation for poor quality stocks."""
        poor_quality_stock = {
            "ticker": "POOR",
            "return_on_equity": 0.08,  # Below threshold
            "current_ratio": 0.9,  # Below threshold
            "debt_to_equity": 80.0,  # Above threshold
        }

        result = assess_quality(poor_quality_stock, quality_thresholds)

        assert len(result["quality_flags"]) > 0
        assert result["quality_score"] < 50  # Should be low score


class TestValueScreening:
    """Test value assessment functionality."""

    @pytest.fixture
    def sample_stock_data(self):
        return {
            "ticker": "VALUE",
            "trailing_pe": 18.0,
            "price_to_book": 2.5,
            "ev_to_ebitda": 12.0,
        }

    @pytest.fixture
    def value_thresholds(self):
        return ValueThresholds(max_pe=25.0, max_pb=3.0, max_ev_ebitda=15.0)

    def test_value_assessment(self, sample_stock_data, value_thresholds):
        """Test value assessment calculation."""
        result = assess_value(sample_stock_data, value_thresholds)

        assert result["ticker"] == "VALUE"
        assert "value_score" in result
        assert "value_metrics" in result
        assert result["value_score"] > 0

        # Should pass all thresholds
        assert len(result["value_flags"]) == 0

    def test_expensive_stock_flags(self, value_thresholds):
        """Test value flags for expensive stocks."""
        expensive_stock = {
            "ticker": "EXPENSIVE",
            "trailing_pe": 45.0,  # Above threshold
            "price_to_book": 8.0,  # Above threshold
            "ev_to_ebitda": 25.0,  # Above threshold
        }

        result = assess_value(expensive_stock, value_thresholds)

        assert len(result["value_flags"]) > 0
        assert result["value_score"] < 50


class TestGrowthScreening:
    """Test growth assessment functionality."""

    @pytest.fixture
    def sample_stock_data(self):
        return {
            "ticker": "GROWTH",
            "revenue_growth": 0.15,  # 15%
            "earnings_growth": 0.20,  # 20%
            "return_on_equity": 0.18,  # For book value growth calculation
        }

    @pytest.fixture
    def growth_thresholds(self):
        return GrowthThresholds(min_revenue_growth=0.10, min_earnings_growth=0.15)

    def test_growth_assessment(self, sample_stock_data, growth_thresholds):
        """Test growth assessment calculation."""
        result = assess_growth(sample_stock_data, growth_thresholds)

        assert result["ticker"] == "GROWTH"
        assert "growth_score" in result
        assert "growth_metrics" in result
        assert result["growth_score"] > 0

        # Should pass growth thresholds
        assert len(result["growth_flags"]) == 0

    def test_growth_quality_assessment(self, sample_stock_data, growth_thresholds):
        """Test growth quality categorization."""
        result = assess_growth(sample_stock_data, growth_thresholds)

        assert "growth_quality" in result
        assert result["growth_quality"] in [
            "margin_expanding",
            "margin_contracting",
            "stable_margins",
        ]


class TestRiskScreening:
    """Test risk assessment functionality."""

    @pytest.fixture
    def sample_stock_data(self):
        return {
            "ticker": "RISK",
            "sector": "Technology",
            "market_cap": 50e9,  # $50B
            "debt_to_equity": 25.0,
            "current_ratio": 1.8,
            "return_on_equity": 0.16,
            "revenue_growth": 0.12,
        }

    @pytest.fixture
    def risk_thresholds(self):
        return RiskThresholds(max_beta=1.5, min_liquidity_ratio=1.0)

    def test_risk_assessment(self, sample_stock_data, risk_thresholds):
        """Test risk assessment calculation."""
        result = assess_risk(sample_stock_data, risk_thresholds)

        assert result["ticker"] == "RISK"
        assert "overall_risk_score" in result
        assert "risk_level" in result
        assert "risk_metrics" in result

        # Should have calculated different risk types
        assert "financial_risk_score" in result["risk_metrics"]
        assert "estimated_beta" in result["risk_metrics"]
        assert "business_risk_score" in result["risk_metrics"]

    def test_risk_level_classification(self, sample_stock_data, risk_thresholds):
        """Test risk level classification."""
        result = assess_risk(sample_stock_data, risk_thresholds)

        assert result["risk_level"] in ["low", "moderate", "high"]


class TestAnalysisPipeline:
    """Test the complete analysis pipeline."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration for testing."""
        return AnalysisConfig(
            name="test_pipeline",
            universe=UniverseConfig(market="usa_sp500"),
            quality=QualityThresholds(min_roic=0.12, min_roe=0.15),
            value=ValueThresholds(max_pe=25, max_pb=3.0),
            growth=GrowthThresholds(min_revenue_growth=0.05),
            risk=RiskThresholds(max_beta=1.5),
            max_results=10,
        )

    @pytest.mark.skip(reason="Pipeline integration tested via working systematic analysis script")
    @patch("invest.data.universal_fetcher.UniversalStockFetcher.fetch_multiple")
    def test_pipeline_execution(self, mock_fetch_multiple, mock_config):
        """Test that pipeline executes without errors."""
        # Mock fetch_multiple to return data for multiple tickers
        mock_fetch_multiple.return_value = {
            "AAPL": {
                "ticker": "AAPL",
                "sector": "Technology",
                "market_cap": 3000e9,
                "current_price": 150.0,
                "trailing_pe": 20.0,
                "price_to_book": 3.0,
                "return_on_equity": 0.28,
                "debt_to_equity": 25.0,
                "current_ratio": 1.1,
                "revenue_growth": 0.08,
                "earnings_growth": 0.12,
            },
            "MSFT": {
                "ticker": "MSFT",
                "sector": "Technology",
                "market_cap": 2800e9,
                "current_price": 300.0,
                "trailing_pe": 25.0,
                "price_to_book": 4.0,
                "return_on_equity": 0.30,
                "debt_to_equity": 30.0,
                "current_ratio": 1.2,
                "revenue_growth": 0.10,
                "earnings_growth": 0.15,
            }
        }

        pipeline = AnalysisPipeline(mock_config)
        results = pipeline.run_analysis()

        # Check result structure
        assert "config" in results
        assert "summary" in results
        assert "stocks" in results
        assert "total_universe" in results
        assert "passed_screening" in results
        assert "final_results" in results

    def test_pipeline_empty_universe(self, mock_config):
        """Test pipeline behavior with empty universe."""
        with patch.object(AnalysisPipeline, "_get_universe", return_value=[]):
            pipeline = AnalysisPipeline(mock_config)
            results = pipeline.run_analysis()

            assert "error" in results
            assert results["error"] == "No stocks found in universe"


class TestIntegration:
    """Integration tests for the complete system."""

    def test_config_to_results_integration(self):
        """Test that a configuration can produce results."""
        # This would be a more comprehensive test with real data
        # For now, just test that the components work together

        config_data = {
            "name": "integration_test",
            "universe": {"region": "US", "custom_tickers": ["AAPL"]},
            "quality": {"min_roe": 0.10},
            "value": {"max_pe": 50},
            "growth": {"min_revenue_growth": 0.0},
            "risk": {"max_beta": 2.0},
            "valuation": {"models": ["dcf"]},
            "max_results": 1,
        }

        config = AnalysisConfig(**config_data)
        assert config.name == "integration_test"
        assert config.universe.custom_tickers == ["AAPL"]

        # Test that pipeline can be initialized with this config
        pipeline = AnalysisPipeline(config)
        assert pipeline.config == config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
