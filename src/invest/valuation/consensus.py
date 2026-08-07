"""
Unified log-return consensus module.

Combines model outputs using weighted geometric mean (log-return averaging),
which is mathematically correct for multiplicative quantities like stock returns.

Core idea:
    log_ratio = ln(fair_value / current_price)   # maps (-1, +inf) return to (-inf, +inf)
    clamp to [-MAX, +MAX]                         # caps at 0.1x to 10x
    weighted average in log space                 # geometric mean
    consensus_fv = current_price * exp(avg_log)   # convert back
"""

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..config.constants import CONSENSUS_CONFIG, ConsensusConfig

logger = logging.getLogger(__name__)


@dataclass
class ModelInput:
    """A single model's valuation input for consensus."""
    model_name: str
    fair_value: float
    confidence: float  # 0-1 numeric


@dataclass
class ConsensusResult:
    """Result of consensus valuation."""
    fair_value: float
    current_price: float
    margin_of_safety: float          # (fv - price) / price
    log_return: float                # ln(fv / price) before clamping
    confidence: str                  # 'high' / 'medium' / 'low'
    num_models: int
    model_weights: Dict[str, float]  # model_name -> final normalized weight


def resolve_confidence(raw: Any, config: ConsensusConfig = None) -> float:
    """Convert confidence to float in [0, 1].

    Accepts:
    - float/int already in [0, 1]
    - str 'high'/'medium'/'low'
    - None -> 0.5 default
    """
    if config is None:
        config = CONSENSUS_CONFIG

    if raw is None:
        return 0.5

    if isinstance(raw, (int, float)):
        return max(0.0, min(1.0, float(raw)))

    if isinstance(raw, str):
        return config.CONFIDENCE_MAP.get(raw.lower(), 0.5)

    return 0.5


def compute_consensus(
    models: List[ModelInput],
    current_price: float,
    config: ConsensusConfig = None,
) -> Optional[ConsensusResult]:
    """Compute consensus fair value using log-return averaging.

    Parameters
    ----------
    models : list of ModelInput
        Each model's name, fair_value, and numeric confidence (0-1).
    current_price : float
        Current market price.
    config : ConsensusConfig, optional
        Override default consensus configuration.

    Returns
    -------
    ConsensusResult or None if no valid models.
    """
    if config is None:
        config = CONSENSUS_CONFIG

    if current_price is None or not math.isfinite(current_price) or current_price <= 0:
        return None

    # 1. Filter valid models
    valid = []
    for m in models:
        if (m.fair_value is not None
                and isinstance(m.fair_value, (int, float))
                and math.isfinite(m.fair_value)
                and m.fair_value > 0):
            valid.append(m)

    if not valid:
        return None

    max_log = config.MAX_ABS_LOG_RATIO

    # 2. Compute log ratios and raw weights
    log_ratios = []
    raw_weights = []
    names = []

    for m in valid:
        lr = math.log(m.fair_value / current_price)
        lr = max(-max_log, min(max_log, lr))  # clamp
        log_ratios.append(lr)

        prior = config.MODEL_WEIGHTS.get(m.model_name, config.DEFAULT_MODEL_WEIGHT)
        if m.model_name not in config.MODEL_WEIGHTS:
            logger.debug(f"Unknown model '{m.model_name}', using default weight {config.DEFAULT_MODEL_WEIGHT}")
        raw_w = prior * m.confidence
        raw_weights.append(raw_w)
        names.append(m.model_name)

    # 3. Normalize weights
    total_raw = sum(raw_weights)
    if total_raw <= 0:
        # Fallback: equal weights
        n = len(valid)
        weights = [1.0 / n] * n
    else:
        weights = [w / total_raw for w in raw_weights]

    # 4. Weighted average in log space
    avg_log = sum(w * lr for w, lr in zip(weights, log_ratios))

    # 5. Convert back
    consensus_fv = current_price * math.exp(avg_log)
    margin = (consensus_fv - current_price) / current_price

    # 6. Determine confidence label (model count + avg weight-adjusted confidence)
    avg_conf = sum(m.confidence * config.MODEL_WEIGHTS.get(m.model_name, config.DEFAULT_MODEL_WEIGHT)
                   for m in valid) / len(valid)
    if len(valid) >= 4 and avg_conf >= 0.5:
        conf_label = 'high'
    elif len(valid) >= 2 and avg_conf >= 0.3:
        conf_label = 'medium'
    else:
        conf_label = 'low'

    # Build weight dict
    model_weights = dict(zip(names, weights))

    return ConsensusResult(
        fair_value=consensus_fv,
        current_price=current_price,
        margin_of_safety=margin,
        log_return=avg_log,
        confidence=conf_label,
        num_models=len(valid),
        model_weights=model_weights,
    )


def compute_consensus_from_dicts(
    valuations: Dict[str, Any],
    current_price: float,
    config: ConsensusConfig = None,
) -> Optional[ConsensusResult]:
    """Adapter for dashboard/scanner dict format.

    Expected format: {model_name: {fair_value, confidence, failed, ...}, ...}
    Also tolerates non-dict entries (like a 'current_price' key) by skipping them.
    """
    if config is None:
        config = CONSENSUS_CONFIG

    inputs = []
    for model_name, val in valuations.items():
        if not isinstance(val, dict):
            continue
        if val.get('failed', False):
            continue

        fv = val.get('fair_value')
        if not isinstance(fv, (int, float)) or fv <= 0:
            continue

        conf = resolve_confidence(val.get('confidence'), config)
        inputs.append(ModelInput(model_name=model_name, fair_value=fv, confidence=conf))

    return compute_consensus(inputs, current_price, config)


def compute_consensus_from_results(
    results: Dict[str, Any],
    current_price: float,
    config: ConsensusConfig = None,
) -> Optional[ConsensusResult]:
    """Adapter for Dict[str, ValuationResult] (ensemble_model.py format).

    ValuationResult has .fair_value (float) and .confidence (str like 'high'/'medium'/'low').
    """
    if config is None:
        config = CONSENSUS_CONFIG

    inputs = []
    for model_name, result in results.items():
        if result is None:
            continue
        fv = getattr(result, 'fair_value', None)
        if fv is None:
            continue

        conf_raw = getattr(result, 'confidence', None)
        conf = resolve_confidence(conf_raw, config)
        inputs.append(ModelInput(model_name=model_name, fair_value=fv, confidence=conf))

    return compute_consensus(inputs, current_price, config)


def consensus_margin_to_rating(margin: float) -> str:
    """Convert margin of safety to a rating string.

    Uses the same thresholds as the existing data_manager.
    """
    if margin > 0.3:
        return "Strong Buy"
    elif margin > 0.15:
        return "Buy"
    elif margin > -0.15:
        return "Hold"
    elif margin > -0.3:
        return "Sell"
    else:
        return "Strong Sell"
