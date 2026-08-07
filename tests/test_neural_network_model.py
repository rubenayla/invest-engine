"""
Test suite for the Neural Network Valuation Model.

Tests the neural network model's initialization, feature extraction,
training capabilities, and valuation methods.
"""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import torch

from src.invest.exceptions import InsufficientDataError
from src.invest.valuation.base import ValuationResult
from src.invest.valuation.neural_network_model import (
    FeatureEngineer,
    NeuralNetworkArchitecture,
    NeuralNetworkValuationModel,
)


class TestFeatureEngineer:
    """Test the feature engineering component."""

    @pytest.fixture
    def feature_engineer(self):
        """Create a feature engineer instance."""
        return FeatureEngineer()

    @pytest.fixture
    def sample_data(self):
        """Create sample financial data."""
        return {
            'info': {
                'currentPrice': 150.0,
                'marketCap': 1000000000,
                'enterpriseValue': 1100000000,
                'totalRevenue': 500000000,
                'trailingEps': 5.0,
                'forwardEps': 6.0,
                'pegRatio': 1.5,
                'priceToBook': 3.0,
                'ebitda': 200000000,
                'profitMargins': 0.2,
                'operatingMargins': 0.25,
                'returnOnEquity': 0.15,
                'returnOnAssets': 0.1,
                'revenueGrowth': 0.1,
                'earningsGrowth': 0.15,
                'currentRatio': 2.0,
                'quickRatio': 1.8,
                'debtToEquity': 0.5,
                'freeCashflow': 100000000,
                'beta': 1.2,
                'dividendYield': 0.02,
                'payoutRatio': 0.3,
                'fiftyTwoWeekHigh': 180.0,
                'fiftyTwoWeekLow': 120.0,
                'fiftyDayAverage': 145.0,
                'twoHundredDayAverage': 140.0,
                'targetMeanPrice': 165.0,
                'numberOfAnalystOpinions': 10,
                'recommendationKey': 'buy',
                'sector': 'Technology',
                'industry': 'Software',
                'sharesOutstanding': 10000000,
                'totalCash': 50000000,
                'totalAssets': 2000000000,
                'totalCurrentLiabilities': 300000000,
                'ebit': 180000000
            }
        }

    def test_extract_features(self, feature_engineer, sample_data):
        """Test feature extraction from financial data."""
        features = feature_engineer.extract_features(sample_data)

        # Check that key features are present
        assert 'pe_ratio' in features
        assert 'forward_pe' in features
        # peg_ratio removed - 100% zeros in cache
        assert 'price_to_book' in features
        assert 'roe' in features
        assert 'profit_margin' in features
        assert 'debt_to_equity' in features
        assert 'beta' in features
        assert 'market_cap_log' in features

        # Check calculations
        assert features['pe_ratio'] == pytest.approx(30.0)  # 150 / 5
        assert features['forward_pe'] == pytest.approx(25.0)  # 150 / 6
        # peg_ratio removed - 100% zeros in cache
        assert features['beta'] == 1.2

    def test_extract_features_with_missing_data(self, feature_engineer):
        """Test feature extraction with missing fields."""
        minimal_data = {
            'info': {
                'currentPrice': 100.0,
                'marketCap': 500000000,
                'enterpriseValue': 550000000,
                'totalRevenue': 100000000
            }
        }

        features = feature_engineer.extract_features(minimal_data)

        # Should still extract features, using defaults for missing data
        assert 'pe_ratio' in features
        assert features['pe_ratio'] == 0.0  # No EPS data
        assert features['beta'] == 1.0  # Default beta

    def test_fit_transform(self, feature_engineer, sample_data):
        """Test fitting and transforming features."""
        # Create multiple samples
        features_list = []
        for i in range(5):
            features = feature_engineer.extract_features(sample_data)
            # Vary some features
            features['pe_ratio'] *= (0.8 + i * 0.1)
            features_list.append(features)

        # Fit and transform
        scaled = feature_engineer.fit_transform(features_list)

        assert scaled.shape[0] == 5
        assert feature_engineer.is_fitted
        assert len(feature_engineer.feature_names) > 0

    def test_transform_requires_fitting(self, feature_engineer, sample_data):
        """Test that transform requires fitting first."""
        features = feature_engineer.extract_features(sample_data)

        with pytest.raises(ValueError, match='must be fitted'):
            feature_engineer.transform(features)


class TestNeuralNetworkArchitecture:
    """Test the neural network architecture."""

    def test_architecture_initialization(self):
        """Test neural network initialization."""
        model = NeuralNetworkArchitecture(input_dim=50, output_type='score')

        # Test forward pass with random input
        x = torch.randn(10, 50)  # Batch of 10 samples, 50 features
        output = model(x)

        assert output.shape == (10, 1)
        # Score output should be in [0, 100]
        assert torch.all(output >= 0)
        assert torch.all(output <= 100)

    def test_architecture_return_output(self):
        """Test neural network with return output type."""
        model = NeuralNetworkArchitecture(input_dim=50, output_type='return')

        x = torch.randn(5, 50)
        output = model(x)

        assert output.shape == (5, 1)
        # Return output can be negative or positive


class TestNeuralNetworkValuationModel:
    """Test the main neural network valuation model."""

    @pytest.fixture
    def model(self):
        """Create a neural network model instance."""
        # Use a non-existent path to prevent auto-loading of real models
        return NeuralNetworkValuationModel(time_horizon='1year', model_path=Path("non_existent_model.pt"))

    @pytest.fixture
    def complete_data(self):
        """Create complete test data."""
        return {
            'info': {
                'currentPrice': 150.0,
                'marketCap': 1000000000,
                'enterpriseValue': 1100000000,
                'totalRevenue': 500000000,
                'trailingEps': 5.0,
                'forwardEps': 6.0,
                'pegRatio': 1.5,
                'priceToBook': 3.0,
                'ebitda': 200000000,
                'profitMargins': 0.2,
                'operatingMargins': 0.25,
                'returnOnEquity': 0.15,
                'returnOnAssets': 0.1,
                'revenueGrowth': 0.1,
                'earningsGrowth': 0.15,
                'currentRatio': 2.0,
                'quickRatio': 1.8,
                'debtToEquity': 0.5,
                'freeCashflow': 100000000,
                'beta': 1.2,
                'dividendYield': 0.02,
                'payoutRatio': 0.3,
                'fiftyTwoWeekHigh': 180.0,
                'fiftyTwoWeekLow': 120.0,
                'fiftyDayAverage': 145.0,
                'twoHundredDayAverage': 140.0,
                'targetMeanPrice': 165.0,
                'numberOfAnalystOpinions': 10,
                'recommendationKey': 'buy',
                'sector': 'Technology',
                'industry': 'Software',
                'sharesOutstanding': 10000000
            },
            'financials': None,
            'balance_sheet': None,
            'cashflow': None
        }

    def test_model_initialization(self, model):
        """Test model initialization."""
        assert model.name == 'neural_network'
        assert model.time_horizon == '1year'
        assert model.model is not None
        assert model.feature_engineer is not None

    def test_is_suitable(self, model, complete_data):
        """Test model suitability check."""
        assert model.is_suitable('TEST', complete_data)

        # Test with insufficient data
        insufficient_data = {
            'info': {
                'currentPrice': 100.0
            }
        }
        assert not model.is_suitable('TEST', insufficient_data)

    def test_validate_inputs(self, model, complete_data):
        """Test input validation."""
        # Should not raise with complete data
        model._validate_inputs('TEST', complete_data)

        # Should raise with missing essential fields
        incomplete_data = {
            'info': {
                'currentPrice': 100.0,
                'marketCap': 1000000
            }
        }

        with pytest.raises(InsufficientDataError):
            model._validate_inputs('TEST', incomplete_data)

    def test_raises_when_untrained(self, model, complete_data):
        """Test that ValuationError is raised when model is not trained."""
        from src.invest.exceptions import ValuationError

        with pytest.raises(ValuationError, match="not trained/loaded"):
            model._calculate_valuation('TEST', complete_data)

    @pytest.mark.slow
    def test_training_workflow(self, model, complete_data):
        """Test the training workflow."""
        # Create training data
        training_data = []
        for i in range(20):
            # Vary the data slightly
            data = complete_data.copy()
            data['info'] = complete_data['info'].copy()
            data['info']['currentPrice'] = 100 + i * 10
            data['info']['trailingEps'] = 3 + i * 0.5

            # Target return (simplified)
            target = 0.1 + (i - 10) * 0.02  # Returns from -10% to +30%

            training_data.append((f'TEST{i}', data, target))

        # Train the model
        metrics = model.train_model(training_data, validation_split=0.2, epochs=10)

        assert 'final_train_loss' in metrics
        assert 'final_val_loss' in metrics
        assert 'train_mae' in metrics
        assert 'val_mae' in metrics
        assert metrics['epochs_trained'] == 10

        # Model should now be fitted
        assert model.feature_engineer.is_fitted

    @pytest.mark.parametrize('time_horizon', ['1month', '1year', '5year'])
    def test_different_time_horizons(self, time_horizon, complete_data):
        """Test model with different time horizons."""
        # Use dummy path to prevent loading real model
        model = NeuralNetworkValuationModel(time_horizon=time_horizon, model_path=Path("dummy"))

        # Fake training to allow valuation
        features = model.feature_engineer.extract_features(complete_data)
        scaled_features = model.feature_engineer.fit_transform([features, features])

        # Re-initialize model with correct input dimension
        input_dim = scaled_features.shape[1]
        model.model = NeuralNetworkArchitecture(
            input_dim=input_dim,
            output_type='score'
        ).to(model.device)

        result = model._calculate_valuation('TEST', complete_data)

        assert result.inputs['time_horizon'] == time_horizon

    def test_save_and_load_model(self, model, tmp_path, complete_data):
        """Test saving and loading model."""
        # First train the model
        training_data = [(f'TEST{i}', complete_data, 0.1) for i in range(20)]
        model.train_model(training_data, epochs=5)

        # Save model
        model_path = tmp_path / 'test_model.pt'
        model.save_model(model_path)

        assert model_path.exists()

        # Load model in new instance
        new_model = NeuralNetworkValuationModel()
        new_model.load_model(model_path)

        assert new_model.feature_engineer.is_fitted
        assert new_model.time_horizon == model.time_horizon

    def test_model_with_extreme_values(self, model):
        """Test model behavior with extreme input values."""
        extreme_data = {
            'info': {
                'currentPrice': 0.01,  # Penny stock
                'marketCap': 1000000,  # Small cap
                'enterpriseValue': 5000000,
                'totalRevenue': 100000,
                'trailingEps': -10.0,  # Negative earnings
                'forwardEps': -5.0,
                'pegRatio': -1.0,
                'debtToEquity': 10.0,  # High debt
                'beta': 3.0,  # Very volatile
                'profitMargins': -0.5  # Negative margins
            }
        }

        # Fake training
        features = model.feature_engineer.extract_features(extreme_data)
        scaled_features = model.feature_engineer.fit_transform([features, features])

        # Re-initialize model with correct input dimension
        input_dim = scaled_features.shape[1]
        model.model = NeuralNetworkArchitecture(
            input_dim=input_dim,
            output_type='score'
        ).to(model.device)

        result = model._calculate_valuation('EXTREME', extreme_data)

        assert isinstance(result, ValuationResult)
        # With random weights, we can't guarantee warnings about overvaluation,
        # but we can check the plumbing holds up.
        # assert len(result.warnings) > 0  # Only works if model logic triggers warnings based on inputs alone
        # The warnings in _generate_warnings are based on FEATURES and SCORE.
        # Features are extreme, so some warnings should appear regardless of score.
        # e.g. "Negative profit margins"
        assert any('Negative profit margins' in w for w in result.warnings)
    def test_feature_importance(self, model, complete_data):
        """Test that top features are extracted correctly."""
        # Fake training
        features = model.feature_engineer.extract_features(complete_data)
        scaled_features = model.feature_engineer.fit_transform([features, features])

        # Re-initialize model with correct input dimension
        input_dim = scaled_features.shape[1]
        model.model = NeuralNetworkArchitecture(
            input_dim=input_dim,
            output_type='score'
        ).to(model.device)

        result = model._calculate_valuation('TEST', complete_data)

        top_features = result.outputs.get('top_features', {})
        if top_features:  # Only if model provides this
            assert isinstance(top_features, dict)
            assert len(top_features) <= 5

    def test_result_types(self, model, complete_data):
        """Test that valuation results are standard python types (not numpy)."""
        # Fake training
        features = model.feature_engineer.extract_features(complete_data)
        scaled_features = model.feature_engineer.fit_transform([features, features])

        input_dim = scaled_features.shape[1]
        model.model = NeuralNetworkArchitecture(
            input_dim=input_dim,
            output_type='score'
        ).to(model.device)

        result = model._calculate_valuation('TEST', complete_data)

        # Check types
        assert isinstance(result.fair_value, float)
        assert not isinstance(result.fair_value, np.number)

        if result.margin_of_safety is not None:
            assert isinstance(result.margin_of_safety, float)
            assert not isinstance(result.margin_of_safety, np.number)

        if result.inputs.get('model_score'):
            assert isinstance(result.inputs['model_score'], float)
            assert not isinstance(result.inputs['model_score'], np.number)

        if result.outputs.get('score'):
            assert isinstance(result.outputs['score'], float)
            assert not isinstance(result.outputs['score'], np.number)

    @patch('torch.cuda.is_available')
    def test_gpu_support(self, mock_cuda, complete_data):
        """Test model initialization with GPU support."""
        # Test with CPU (most test environments)
        mock_cuda.return_value = False
        model = NeuralNetworkValuationModel()
        assert model.device.type == 'cpu'

        # Note: We can't easily test CUDA initialization without a GPU
        # as moving tensors to cuda will fail in CPU-only environments


class TestIntegrationWithRegistry:
    """Test integration with the model registry."""

    def test_model_in_registry(self):
        """Test that neural network model is registered."""
        from src.invest.valuation.model_registry import ModelRegistry

        registry = ModelRegistry()
        available = registry.get_available_models()

        assert 'neural_network' in available

        # Test instantiation through registry
        model = registry.get_model('neural_network')
        assert isinstance(model, NeuralNetworkValuationModel)

    def test_model_metadata(self):
        """Test model metadata in registry."""
        from src.invest.valuation.model_registry import ModelRegistry

        registry = ModelRegistry()
        metadata = registry.get_model_metadata('neural_network')

        assert metadata['name'] == 'Neural Network Valuation'
        assert 'ML-based' in metadata['description']
        assert metadata['complexity'] == 'very high'

    def test_model_requirements(self):
        """Test model data requirements."""
        from src.invest.valuation.model_requirements import ModelDataRequirements

        requirements = ModelDataRequirements.get_requirements('neural_network')

        assert 'currentPrice' in requirements.required
        assert 'marketCap' in requirements.required
        assert 'enterpriseValue' in requirements.required
        assert 'totalRevenue' in requirements.required
        assert len(requirements.optional) > 10  # Many optional features
