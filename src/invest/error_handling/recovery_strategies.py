"""
Error recovery strategies for graceful degradation and automatic error recovery.

This module provides specific recovery strategies for different types of errors,
enabling the system to automatically recover from failures and provide fallback
functionality when possible.
"""

import random
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

from ..config.logging_config import get_logger
from ..exceptions import DataFetchError, ModelNotSuitableError, RateLimitError, ValidationError
from .error_manager import ErrorInfo

logger = get_logger(__name__)


class RecoveryStrategy:
    """Base class for recovery strategies."""

    def __init__(self, name: str, max_attempts: int = 3):
        self.name = name
        self.max_attempts = max_attempts
        self.success_count = 0
        self.failure_count = 0

    def attempt_recovery(self, error_info: ErrorInfo) -> bool:
        """
        Attempt to recover from the error.

        Returns:
            True if recovery was successful, False otherwise
        """
        raise NotImplementedError

    def get_success_rate(self) -> float:
        """Get the success rate of this recovery strategy."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0


class RetryWithBackoffStrategy(RecoveryStrategy):
    """Retry the operation with exponential backoff."""

    def __init__(self, max_attempts: int = 3, base_delay: float = 1.0, max_delay: float = 60.0):
        super().__init__("retry_with_backoff", max_attempts)
        self.base_delay = base_delay
        self.max_delay = max_delay

    def attempt_recovery(self, error_info: ErrorInfo) -> bool:
        """Retry the operation with exponential backoff."""
        if not error_info.retry_possible:
            return False

        logger.info(f"Attempting recovery with retry strategy for {error_info.error_id}")

        for attempt in range(self.max_attempts):
            # Calculate delay with jitter
            delay = min(
                self.base_delay * (2 ** attempt) + random.uniform(0, 1),
                self.max_delay
            )

            if attempt > 0:  # Don't delay on first attempt
                logger.info(f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{self.max_attempts})")
                time.sleep(delay)

            # Note: Actual retry logic would need to be implemented by the calling code
            # This strategy just provides the backoff timing
            logger.info(f"Retry attempt {attempt + 1} ready for {error_info.error_id}")

        # For now, we can't actually retry operations automatically
        # This would require callback functions or operation objects
        return False


class FallbackDataStrategy(RecoveryStrategy):
    """Use fallback data sources when primary fails."""

    def __init__(self):
        super().__init__("fallback_data")
        self.fallback_providers = ['mock_provider']  # Could include other providers

    def attempt_recovery(self, error_info: ErrorInfo) -> bool:
        """Attempt to use fallback data provider."""
        if not isinstance(error_info.exception, (DataFetchError, RateLimitError)):
            return False

        logger.info(f"Attempting fallback data recovery for {error_info.error_id}")

        try:
            # This would need integration with the data provider system
            from ..data.providers import get_provider_manager, setup_default_providers

            manager = get_provider_manager()

            # If primary provider is failing, try fallbacks
            if manager.fallback_providers:
                logger.info("Fallback providers available, recovery handled by provider manager")
                self.success_count += 1
                return True
            else:
                # Setup mock provider as emergency fallback
                setup_default_providers(use_mock=True, mock_failure_rate=0.1)
                logger.info("Setup mock provider as emergency fallback")
                self.success_count += 1
                return True

        except Exception as e:
            logger.error(f"Fallback data recovery failed: {e}")
            self.failure_count += 1
            return False


class ModelSubstitutionStrategy(RecoveryStrategy):
    """Substitute unsuitable valuation models with alternatives."""

    def __init__(self):
        super().__init__("model_substitution")
        # Define model substitution hierarchy
        self.model_substitutions = {
            'dcf': ['simple_ratios', 'rim'],
            'enhanced_dcf': ['dcf', 'simple_ratios'],
            'multi_stage_dcf': ['dcf', 'simple_ratios'],
            'monte_carlo_dcf': ['dcf', 'simple_ratios'],
            'rim': ['simple_ratios', 'dcf']
        }

    def attempt_recovery(self, error_info: ErrorInfo) -> bool:
        """Attempt to substitute with alternative valuation model."""
        if not isinstance(error_info.exception, ModelNotSuitableError):
            return False

        if not error_info.context.model:
            return False

        failed_model = error_info.context.model.lower()
        alternatives = self.model_substitutions.get(failed_model, ['simple_ratios'])

        logger.info(f"Model substitution: {failed_model} -> {alternatives} for {error_info.context.ticker}")

        # Log the recommendation (actual substitution would need to be handled by calling code)
        self.success_count += 1
        return True  # Always return True as we can always recommend Simple Ratios


class GracefulDegradationStrategy(RecoveryStrategy):
    """Provide partial results when complete analysis fails."""

    def __init__(self):
        super().__init__("graceful_degradation")

    def attempt_recovery(self, error_info: ErrorInfo) -> bool:
        """Attempt graceful degradation to partial functionality."""

        # For valuation errors, suggest what data is still available
        if isinstance(error_info.exception, (ModelNotSuitableError, ValidationError)):
            logger.info(f"Graceful degradation: recommending basic analysis for {error_info.context.ticker}")

            # Could provide partial analysis suggestions:
            # - Current price and basic ratios
            # - Sector comparison
            # - Simple momentum indicators

            self.success_count += 1
            return True

        return False


class UserGuidanceStrategy(RecoveryStrategy):
    """Provide enhanced user guidance for common issues."""

    def __init__(self):
        super().__init__("user_guidance")

    def attempt_recovery(self, error_info: ErrorInfo) -> bool:
        """Provide enhanced guidance to help user resolve the issue."""

        guidance_messages = {
            DataFetchError: self._generate_data_fetch_guidance,
            RateLimitError: self._generate_rate_limit_guidance,
            ValidationError: self._generate_validation_guidance,
            ModelNotSuitableError: self._generate_model_guidance
        }

        exception_type = type(error_info.exception)
        if exception_type in guidance_messages:
            enhanced_guidance = guidance_messages[exception_type](error_info)
            logger.info(f"Enhanced user guidance provided for {error_info.error_id}: {enhanced_guidance}")
            self.success_count += 1
            return True

        return False

    def _generate_data_fetch_guidance(self, error_info: ErrorInfo) -> str:
        """Generate specific guidance for data fetch errors."""
        ticker = error_info.context.ticker or "the stock"

        if "not found" in str(error_info.exception).lower():
            return f"Ticker '{ticker}' was not found. Try: 1) Check spelling, 2) Use full ticker (e.g., BRK-A not BRK.A), 3) Verify the stock is publicly traded"
        elif "delisted" in str(error_info.exception).lower():
            return f"Stock '{ticker}' appears to be delisted. Try searching for the current ticker symbol or use a different stock"
        else:
            return f"Data access issue for '{ticker}'. Try: 1) Check internet connection, 2) Wait 30 seconds, 3) Use a well-known ticker like AAPL for testing"

    def _generate_rate_limit_guidance(self, error_info: ErrorInfo) -> str:
        """Generate specific guidance for rate limit errors."""
        return "Rate limit reached. Solutions: 1) Wait 60 seconds, 2) Analyze fewer stocks at once, 3) Enable the concurrent data fetching which includes rate limiting"

    def _generate_validation_guidance(self, error_info: ErrorInfo) -> str:
        """Generate specific guidance for validation errors."""
        return f"Input validation failed: {error_info.exception}. Try: 1) Check input format, 2) Use example values from documentation, 3) Ensure numeric inputs are valid numbers"

    def _generate_model_guidance(self, error_info: ErrorInfo) -> str:
        """Generate specific guidance for model suitability errors."""
        ticker = error_info.context.ticker or "this stock"
        model = error_info.context.model or "the selected model"

        model_alternatives = {
            'dcf': 'Try Simple Ratios or RIM models instead',
            'enhanced_dcf': 'Try basic DCF or Simple Ratios models',
            'rim': 'Try DCF or Simple Ratios models',
            'multi_stage_dcf': 'Try basic DCF model for more stable companies'
        }

        alternative = model_alternatives.get(model.lower(), 'Try the Simple Ratios model as it works for most stocks')

        return f"{model} not suitable for {ticker}. {alternative}. The issue is likely due to insufficient financial history or unusual business model"


class SystemHealthStrategy(RecoveryStrategy):
    """Monitor and improve system health based on error patterns."""

    def __init__(self):
        super().__init__("system_health")
        self.error_patterns: Dict[str, int] = {}
        self.last_health_check = datetime.now()

    def attempt_recovery(self, error_info: ErrorInfo) -> bool:
        """Analyze error patterns and suggest system improvements."""

        # Track error patterns
        pattern_key = f"{error_info.category.value}_{type(error_info.exception).__name__}"
        self.error_patterns[pattern_key] = self.error_patterns.get(pattern_key, 0) + 1

        # Periodic health analysis
        if datetime.now() - self.last_health_check > timedelta(hours=1):
            self._analyze_system_health()
            self.last_health_check = datetime.now()

        return True  # Always successful as it's monitoring

    def _analyze_system_health(self):
        """Analyze system health based on error patterns."""
        if not self.error_patterns:
            return

        # Find most common error patterns
        top_patterns = sorted(self.error_patterns.items(), key=lambda x: x[1], reverse=True)[:5]

        health_report = {
            "timestamp": datetime.now().isoformat(),
            "top_error_patterns": top_patterns,
            "total_errors_tracked": sum(self.error_patterns.values()),
            "recommendations": self._generate_health_recommendations(top_patterns)
        }

        logger.info("System health analysis completed", extra=health_report)

    def _generate_health_recommendations(self, top_patterns: List[tuple]) -> List[str]:
        """Generate system health recommendations based on error patterns."""
        recommendations = []

        for pattern, count in top_patterns:
            if "data_access_DataFetchError" in pattern and count > 10:
                recommendations.append("Consider enabling data provider fallbacks or checking network stability")
            elif "validation_ValidationError" in pattern and count > 5:
                recommendations.append("Review input validation rules and user guidance")
            elif "calculation_ModelNotSuitableError" in pattern and count > 8:
                recommendations.append("Implement better pre-screening for model suitability")

        if len(top_patterns) > 0 and sum(count for _, count in top_patterns) > 50:
            recommendations.append("High error rate detected - consider system maintenance")

        return recommendations


class RecoveryManager:
    """Manages multiple recovery strategies and coordinates their execution."""

    def __init__(self):
        self.strategies: Dict[str, RecoveryStrategy] = {}
        self.strategy_priority: List[str] = []

        # Register default strategies
        self._register_default_strategies()

    def _register_default_strategies(self):
        """Register default recovery strategies."""
        strategies = [
            FallbackDataStrategy(),
            ModelSubstitutionStrategy(),
            GracefulDegradationStrategy(),
            UserGuidanceStrategy(),
            RetryWithBackoffStrategy(),
            SystemHealthStrategy()
        ]

        for strategy in strategies:
            self.register_strategy(strategy)

    def register_strategy(self, strategy: RecoveryStrategy, priority: int = None):
        """Register a recovery strategy."""
        self.strategies[strategy.name] = strategy

        if priority is None:
            self.strategy_priority.append(strategy.name)
        else:
            self.strategy_priority.insert(priority, strategy.name)

    def attempt_recovery(self, error_info: ErrorInfo) -> List[str]:
        """Attempt recovery using all applicable strategies."""
        successful_strategies = []

        for strategy_name in self.strategy_priority:
            strategy = self.strategies[strategy_name]

            try:
                if strategy.attempt_recovery(error_info):
                    successful_strategies.append(strategy_name)
                    logger.debug(f"Recovery strategy '{strategy_name}' succeeded for {error_info.error_id}")
                else:
                    logger.debug(f"Recovery strategy '{strategy_name}' not applicable for {error_info.error_id}")
            except Exception as e:
                logger.warning(f"Recovery strategy '{strategy_name}' failed: {e}")

        return successful_strategies

    def get_strategy_statistics(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all recovery strategies."""
        stats = {}

        for name, strategy in self.strategies.items():
            stats[name] = {
                "success_count": strategy.success_count,
                "failure_count": strategy.failure_count,
                "success_rate": strategy.get_success_rate(),
                "max_attempts": strategy.max_attempts
            }

        return stats


# Global recovery manager instance
recovery_manager = RecoveryManager()
