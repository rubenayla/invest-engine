"""
Centralized configuration constants for the investment analysis system.

This module contains all hard-coded values that were previously scattered
throughout the codebase, making them easily configurable and maintainable.
"""

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class AnalysisLimits:
    """Analysis processing limits and constraints."""

    # Data fetching limits
    MAX_TICKERS_FOR_MARKET_CAP_FETCH: int = 150
    MARKET_CAP_FETCH_MULTIPLIER: float = 1.5
    DEFAULT_TIMEOUT_PER_STOCK: int = 30
    MAX_CONCURRENT_REQUESTS: int = 10

    # Screening thresholds
    MIN_QUALITY_SCORE: float = 40.0
    MIN_VALUE_SCORE: float = 30.0
    MIN_GROWTH_SCORE: float = 20.0
    MAX_RISK_SCORE: float = 80.0
    MIN_COMPOSITE_SCORE: float = 50.0


@dataclass(frozen=True)
class ValuationDefaults:
    """Default parameters for valuation models."""

    # DCF Model defaults
    DCF_PROJECTION_YEARS: int = 10
    DCF_TERMINAL_GROWTH: float = 0.025
    DCF_DISCOUNT_RATE: float = 0.12
    TERMINAL_GROWTH_RATE: float = 0.025

    # Growth and risk parameters
    DEFAULT_GROWTH_RATE: float = 0.05
    MAX_GROWTH_RATE: float = 0.25
    RISK_FREE_RATE: float = 0.045
    EQUITY_RISK_PREMIUM: float = 0.065

    # RIM Model defaults
    RIM_PROJECTION_YEARS: int = 10
    RIM_COST_OF_EQUITY: float = 0.12
    RIM_ROE_DECAY_RATE: float = 0.05
    RIM_MAX_SUSTAINABLE_ROE: float = 0.30
    ROE_FADE_RATE: float = 0.7  # How much ROE fades toward cost of equity
    RETENTION_RATIO: float = 0.6  # Portion of earnings retained

    # Enhanced DCF defaults
    ENHANCED_DCF_PROJECTION_YEARS: int = 10
    ENHANCED_DCF_TERMINAL_GROWTH: float = 0.025

    # Multi-stage DCF defaults
    MULTI_STAGE_HIGH_GROWTH_YEARS: int = 5
    MULTI_STAGE_TRANSITION_YEARS: int = 5

    # Simple ratios defaults (industry multiples)
    DEFAULT_PE_MULTIPLE: float = 15.0
    DEFAULT_PB_MULTIPLE: float = 1.5
    DEFAULT_PS_MULTIPLE: float = 2.0
    DEFAULT_PCF_MULTIPLE: float = 10.0


@dataclass(frozen=True)
class DataProviderConfig:
    """Configuration for external data providers."""

    # Rate limiting
    REQUESTS_PER_SECOND: float = 2.0  # Conservative limit for Yahoo Finance
    REQUESTS_PER_MINUTE: int = 100
    MAX_CONCURRENT_REQUESTS: int = 10
    RETRY_DELAY_SECONDS: float = 1.0
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_MULTIPLIER: int = 2
    RETRY_MAX_WAIT: int = 60

    # Cache settings
    CACHE_EXPIRY_HOURS: int = 24
    MAX_CACHE_SIZE_MB: int = 100


@dataclass(frozen=True)
class ConsensusConfig:
    """Configuration for consensus valuation (log-return averaging)."""

    # Per-model prior weights (higher = more trusted)
    MODEL_WEIGHTS: Dict[str, float] = field(default_factory=lambda: {
        # GBM models (most trusted — strong empirical correlation)
        'gbm_3y': 1.3,
        'gbm_opportunistic_3y': 1.3,
        'gbm_1y': 1.1,
        'gbm_opportunistic_1y': 1.1,
        'gbm_lite_3y': 1.0,
        'gbm_lite_1y': 0.9,

        # DCF models (solid theoretical foundation)
        'dcf_enhanced': 0.9,
        'growth_dcf': 0.9,
        'dcf': 0.8,
        'multi_stage_dcf': 0.7,

        # Other fundamental models
        'rim': 0.7,
        'simple_ratios': 0.4,

        # Sector-specific (authoritative when applicable)
        'reit': 0.9,
        'bank': 0.9,
        'tech': 0.8,
        'utility': 0.8,

        # Ensemble / multi-horizon (meta-models)
        'ensemble': 0.6,
        # 'multi_horizon_nn': 0.4,  # Disabled: near-zero test correlation (2026-02-21)

        # Neural network models (less trusted)
        'neural_network_best': 0.5,
        'neural_network_consensus': 0.4,
        'neural_network': 0.3,
        'neural_network_1year': 0.3,
    })

    # Confidence string → numeric mapping
    CONFIDENCE_MAP: Dict[str, float] = field(default_factory=lambda: {
        'high': 0.9,
        'medium': 0.5,
        'low': 0.2,
    })

    MAX_ABS_LOG_RATIO: float = 2.3     # ln(10) ≈ caps at 10x / 0.1x
    DEFAULT_MODEL_WEIGHT: float = 0.5  # for unknown models


@dataclass(frozen=True)
class DashboardConfig:
    """Dashboard-specific configuration."""

    # Update settings
    AUTO_REFRESH_INTERVAL_SECONDS: int = 10
    MAX_STOCKS_PER_UPDATE: int = 50

    # Display settings
    MAX_TOOLTIP_LENGTH: int = 100
    DECIMAL_PLACES: int = 2


# Global configuration instance
ANALYSIS_LIMITS = AnalysisLimits()
VALUATION_DEFAULTS = ValuationDefaults()
DATA_PROVIDER_CONFIG = DataProviderConfig()
CONSENSUS_CONFIG = ConsensusConfig()
DASHBOARD_CONFIG = DashboardConfig()


def get_config_summary() -> Dict[str, Any]:
    """Get a summary of all configuration values for debugging."""
    return {
        "analysis_limits": ANALYSIS_LIMITS.__dict__,
        "valuation_defaults": VALUATION_DEFAULTS.__dict__,
        "data_provider_config": DATA_PROVIDER_CONFIG.__dict__,
        "consensus_config": {
            "max_abs_log_ratio": CONSENSUS_CONFIG.MAX_ABS_LOG_RATIO,
            "default_model_weight": CONSENSUS_CONFIG.DEFAULT_MODEL_WEIGHT,
            "num_models": len(CONSENSUS_CONFIG.MODEL_WEIGHTS),
        },
        "dashboard_config": DASHBOARD_CONFIG.__dict__,
    }
