"""Tests for the unified consensus module."""

import math

import pytest

from invest.config.constants import ConsensusConfig
from invest.valuation.consensus import (
    ConsensusResult,
    ModelInput,
    compute_consensus,
    compute_consensus_from_dicts,
    compute_consensus_from_results,
    consensus_margin_to_rating,
    resolve_confidence,
)


# ---------------------------------------------------------------------------
# resolve_confidence
# ---------------------------------------------------------------------------

class TestResolveConfidence:
    def test_none_returns_default(self):
        assert resolve_confidence(None) == 0.5

    def test_string_high(self):
        assert resolve_confidence('high') == 0.9

    def test_string_medium(self):
        assert resolve_confidence('medium') == 0.5

    def test_string_low(self):
        assert resolve_confidence('low') == 0.2

    def test_string_case_insensitive(self):
        assert resolve_confidence('HIGH') == 0.9

    def test_float_passthrough(self):
        assert resolve_confidence(0.75) == 0.75

    def test_float_clamped_above(self):
        assert resolve_confidence(1.5) == 1.0

    def test_float_clamped_below(self):
        assert resolve_confidence(-0.3) == 0.0

    def test_unknown_string_returns_default(self):
        assert resolve_confidence('unknown') == 0.5


# ---------------------------------------------------------------------------
# compute_consensus — core algorithm
# ---------------------------------------------------------------------------

class TestComputeConsensus:
    """Test the core log-return averaging algorithm."""

    def test_symmetry_2x_and_half(self):
        """2x and 0.5x should average to 1.0x (geometric mean), not 1.25x (arithmetic)."""
        price = 100.0
        models = [
            ModelInput('a', fair_value=200.0, confidence=1.0),  # 2x
            ModelInput('b', fair_value=50.0, confidence=1.0),   # 0.5x
        ]
        # Use equal prior weights
        config = ConsensusConfig(MODEL_WEIGHTS={'a': 1.0, 'b': 1.0})
        result = compute_consensus(models, price, config)
        assert result is not None
        assert abs(result.fair_value - 100.0) < 0.01  # geometric mean = 1.0x

    def test_single_model(self):
        """Single model should pass through its own fair value."""
        price = 50.0
        models = [ModelInput('dcf', fair_value=75.0, confidence=1.0)]
        config = ConsensusConfig(MODEL_WEIGHTS={'dcf': 1.0})
        result = compute_consensus(models, price, config)
        assert result is not None
        assert abs(result.fair_value - 75.0) < 0.01
        assert result.num_models == 1
        assert result.model_weights['dcf'] == 1.0

    def test_weighting(self):
        """Higher-weighted model should pull consensus toward its value."""
        price = 100.0
        models = [
            ModelInput('trusted', fair_value=200.0, confidence=1.0),
            ModelInput('weak', fair_value=50.0, confidence=1.0),
        ]
        config = ConsensusConfig(MODEL_WEIGHTS={'trusted': 3.0, 'weak': 1.0})
        result = compute_consensus(models, price, config)
        assert result is not None
        # trusted has 3x weight, so consensus should be pulled toward 200
        assert result.fair_value > 100.0

    def test_confidence_weighting(self):
        """Low-confidence model should have less influence."""
        price = 100.0
        models = [
            ModelInput('a', fair_value=200.0, confidence=1.0),
            ModelInput('b', fair_value=50.0, confidence=0.1),  # very low confidence
        ]
        config = ConsensusConfig(MODEL_WEIGHTS={'a': 1.0, 'b': 1.0})
        result = compute_consensus(models, price, config)
        assert result is not None
        # b has very low confidence so consensus should be close to 200
        assert result.fair_value > 150.0

    def test_clamping_extreme_high(self):
        """Extreme fair value (1000x) should be clamped to ~10x."""
        price = 100.0
        models = [ModelInput('crazy', fair_value=100_000.0, confidence=1.0)]
        config = ConsensusConfig(MODEL_WEIGHTS={'crazy': 1.0})
        result = compute_consensus(models, price, config)
        assert result is not None
        # Clamped at e^2.3 ≈ 9.97x
        assert result.fair_value < price * 11
        assert result.fair_value > price * 9

    def test_clamping_extreme_low(self):
        """Extreme low fair value (0.001x) should be clamped to ~0.1x."""
        price = 100.0
        models = [ModelInput('crazy', fair_value=0.1, confidence=1.0)]
        config = ConsensusConfig(MODEL_WEIGHTS={'crazy': 1.0})
        result = compute_consensus(models, price, config)
        assert result is not None
        # Clamped at e^-2.3 ≈ 0.1x
        assert result.fair_value > price * 0.09
        assert result.fair_value < price * 0.12

    def test_no_valid_models_returns_none(self):
        result = compute_consensus([], 100.0)
        assert result is None

    def test_invalid_price_returns_none(self):
        models = [ModelInput('a', fair_value=100.0, confidence=1.0)]
        assert compute_consensus(models, 0.0) is None
        assert compute_consensus(models, -10.0) is None
        assert compute_consensus(models, float('nan')) is None

    def test_filters_invalid_fair_values(self):
        """Models with non-positive or non-finite fair values should be filtered."""
        price = 100.0
        models = [
            ModelInput('good', fair_value=150.0, confidence=1.0),
            ModelInput('bad_zero', fair_value=0.0, confidence=1.0),
            ModelInput('bad_neg', fair_value=-50.0, confidence=1.0),
            ModelInput('bad_nan', fair_value=float('nan'), confidence=1.0),
            ModelInput('bad_inf', fair_value=float('inf'), confidence=1.0),
        ]
        config = ConsensusConfig(MODEL_WEIGHTS={
            'good': 1.0, 'bad_zero': 1.0, 'bad_neg': 1.0,
            'bad_nan': 1.0, 'bad_inf': 1.0,
        })
        result = compute_consensus(models, price, config)
        assert result is not None
        assert result.num_models == 1
        assert abs(result.fair_value - 150.0) < 0.01

    def test_all_zero_weights_fallback_to_equal(self):
        """If all raw weights are 0, should use equal weights."""
        price = 100.0
        models = [
            ModelInput('a', fair_value=200.0, confidence=0.0),
            ModelInput('b', fair_value=50.0, confidence=0.0),
        ]
        config = ConsensusConfig(MODEL_WEIGHTS={'a': 1.0, 'b': 1.0})
        result = compute_consensus(models, price, config)
        assert result is not None
        # Equal weights in log space → geometric mean = sqrt(200*50) = 100
        assert abs(result.fair_value - 100.0) < 0.01

    def test_unknown_model_uses_default_weight(self):
        """Unknown model names should get DEFAULT_MODEL_WEIGHT."""
        price = 100.0
        models = [ModelInput('unknown_model', fair_value=150.0, confidence=1.0)]
        config = ConsensusConfig(
            MODEL_WEIGHTS={},
            DEFAULT_MODEL_WEIGHT=0.5,
        )
        result = compute_consensus(models, price, config)
        assert result is not None
        assert abs(result.fair_value - 150.0) < 0.01

    def test_confidence_label_by_count(self):
        """Confidence label depends on number of valid models."""
        price = 100.0
        config = ConsensusConfig(MODEL_WEIGHTS={'a': 1.0, 'b': 1.0, 'c': 1.0, 'd': 1.0})

        # 1 model -> low
        r1 = compute_consensus([ModelInput('a', 150.0, 1.0)], price, config)
        assert r1.confidence == 'low'

        # 2 models -> medium
        r2 = compute_consensus([ModelInput('a', 150.0, 1.0), ModelInput('b', 120.0, 1.0)], price, config)
        assert r2.confidence == 'medium'

        # 4 models -> high
        r4 = compute_consensus([
            ModelInput('a', 150.0, 1.0), ModelInput('b', 120.0, 1.0),
            ModelInput('c', 130.0, 1.0), ModelInput('d', 110.0, 1.0),
        ], price, config)
        assert r4.confidence == 'high'


# ---------------------------------------------------------------------------
# Adapter: compute_consensus_from_dicts
# ---------------------------------------------------------------------------

class TestConsensusFromDicts:
    def test_basic(self):
        valuations = {
            'dcf': {'fair_value': 150.0, 'confidence': 'high'},
            'rim': {'fair_value': 120.0, 'confidence': 'medium'},
        }
        result = compute_consensus_from_dicts(valuations, 100.0)
        assert result is not None
        assert result.num_models == 2
        assert result.fair_value > 0

    def test_skips_failed(self):
        valuations = {
            'dcf': {'fair_value': 150.0, 'confidence': 'high'},
            'rim': {'fair_value': 120.0, 'confidence': 'medium', 'failed': True},
        }
        result = compute_consensus_from_dicts(valuations, 100.0)
        assert result.num_models == 1

    def test_skips_non_dict(self):
        """Non-dict values like current_price should be skipped."""
        valuations = {
            'dcf': {'fair_value': 150.0, 'confidence': 'high'},
            'current_price': 100.0,  # not a dict
        }
        result = compute_consensus_from_dicts(valuations, 100.0)
        assert result.num_models == 1

    def test_numeric_confidence(self):
        valuations = {
            'dcf': {'fair_value': 150.0, 'confidence': 0.85},
        }
        result = compute_consensus_from_dicts(valuations, 100.0)
        assert result is not None

    def test_empty_valuations(self):
        result = compute_consensus_from_dicts({}, 100.0)
        assert result is None


# ---------------------------------------------------------------------------
# Adapter: compute_consensus_from_results
# ---------------------------------------------------------------------------

class TestConsensusFromResults:
    def test_basic_with_mock_result(self):
        class MockResult:
            def __init__(self, fv, conf):
                self.fair_value = fv
                self.confidence = conf

        results = {
            'dcf': MockResult(150.0, 'high'),
            'rim': MockResult(120.0, 'medium'),
        }
        result = compute_consensus_from_results(results, 100.0)
        assert result is not None
        assert result.num_models == 2

    def test_skips_none_results(self):
        class MockResult:
            def __init__(self, fv, conf):
                self.fair_value = fv
                self.confidence = conf

        results = {
            'dcf': MockResult(150.0, 'high'),
            'rim': None,
        }
        result = compute_consensus_from_results(results, 100.0)
        assert result.num_models == 1


# ---------------------------------------------------------------------------
# consensus_margin_to_rating
# ---------------------------------------------------------------------------

class TestMarginToRating:
    def test_strong_buy(self):
        assert consensus_margin_to_rating(0.5) == "Strong Buy"

    def test_buy(self):
        assert consensus_margin_to_rating(0.2) == "Buy"

    def test_hold(self):
        assert consensus_margin_to_rating(0.0) == "Hold"

    def test_sell(self):
        assert consensus_margin_to_rating(-0.2) == "Sell"

    def test_strong_sell(self):
        assert consensus_margin_to_rating(-0.5) == "Strong Sell"

    def test_boundary_strong_buy(self):
        assert consensus_margin_to_rating(0.3001) == "Strong Buy"

    def test_boundary_buy(self):
        assert consensus_margin_to_rating(0.15001) == "Buy"
