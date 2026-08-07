"""
ValuationEngine - Handles execution and coordination of valuation models.

This component is responsible for:
- Running individual valuation models safely with timeouts
- Handling model-specific errors and failures
- Formatting and cleaning valuation results
- Managing concurrent model execution
"""

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Any, Dict, Optional

# Import error handling
from ..exceptions import InsufficientDataError, ModelNotSuitableError, ValuationError

# Import unified valuation models
from ..valuation.model_registry import ModelRegistry

logger = logging.getLogger(__name__)


class ValuationEngine:
    """Handles safe execution of valuation models with error handling and timeouts."""

    def __init__(self):
        """Initialize the valuation engine."""
        self.model_registry = ModelRegistry()
        self.model_stats = {
            model: {'attempts': 0, 'successes': 0, 'failures': 0}
            for model in self.model_registry.get_available_models()
        }

    def run_valuation(self, ticker: str, model: str, timeout: int = 30) -> Optional[Dict]:
        """
        Run a single valuation model safely with timeout and error handling.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol
        model : str
            Valuation model name ('dcf', 'rim', etc.)
        timeout : int
            Timeout in seconds for the valuation

        Returns
        -------
        Optional[Dict]
            Valuation result or None if failed
        """
        if model not in self.model_registry.get_available_models():
            logger.error(f"Unknown valuation model: {model}")
            return None

        self.model_stats[model]['attempts'] += 1

        try:
            # Run valuation with timeout using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self._execute_model, ticker, model)
                result = future.result(timeout=timeout)

            if result:
                self.model_stats[model]['successes'] += 1
                logger.debug(f"Valuation successful: {ticker} {model}")
                return result
            else:
                self.model_stats[model]['failures'] += 1
                return None

        except TimeoutError:
            logger.warning(f"Valuation timeout: {ticker} {model} (>{timeout}s)")
            self.model_stats[model]['failures'] += 1
            return None

        except Exception as e:
            logger.error(f"Valuation error: {ticker} {model} - {e}")
            self.model_stats[model]['failures'] += 1
            return None

    def _execute_model(self, ticker: str, model: str) -> Optional[Dict]:
        """Execute the valuation model using the unified registry."""
        try:
            # Use the model registry to run the valuation
            result = self.model_registry.run_valuation(model, ticker, verbose=False)

            if result and result.is_valid():
                return result.to_dict()
            else:
                return None

        except ModelNotSuitableError as e:
            logger.info(f"Model {model} not suitable for {ticker}: {e}")
            return None

        except InsufficientDataError as e:
            logger.info(f"Insufficient data for {ticker} {model}: {e}")
            return None

        except ValuationError as e:
            logger.warning(f"Valuation error for {ticker} {model}: {e}")
            return None

        except Exception as e:
            logger.error(f"Unexpected error in {ticker} {model}: {e}")
            return None

    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float, handling None and invalid values."""
        try:
            if value is None:
                return None
            return float(value)
        except (ValueError, TypeError):
            return None

    def get_model_statistics(self) -> Dict[str, Dict]:
        """Get statistics for all models."""
        stats = {}
        for model, data in self.model_stats.items():
            total = data['attempts']
            success_rate = (data['successes'] / total) if total > 0 else 0

            stats[model] = {
                'attempts': total,
                'successes': data['successes'],
                'failures': data['failures'],
                'success_rate': success_rate,
            }

        return stats

    def get_available_models(self) -> list:
        """Get list of available valuation models."""
        return self.model_registry.get_available_models()

    def reset_statistics(self):
        """Reset all model statistics."""
        for model in self.model_stats:
            self.model_stats[model] = {'attempts': 0, 'successes': 0, 'failures': 0}

        logger.info("Valuation engine statistics reset")
