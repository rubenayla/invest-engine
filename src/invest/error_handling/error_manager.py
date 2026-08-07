"""
Comprehensive error handling system for the investment analysis framework.

This module provides centralized error handling, user-friendly error messages,
error recovery strategies, and error reporting for better system reliability
and user experience.

Key Features:
- Centralized error handling and recovery
- User-friendly error messages and suggestions
- Error categorization and severity levels
- Automatic error reporting and logging
- Graceful degradation strategies
- Error context preservation
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..config.logging_config import get_logger
from ..exceptions import (
    AnalysisError,
    DataFetchError,
    InsufficientDataError,
    ModelNotSuitableError,
    RateLimitError,
    ValidationError,
    ValuationError,
)

logger = get_logger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels for categorization."""
    CRITICAL = "critical"     # System cannot continue
    HIGH = "high"            # Feature unavailable, but system continues
    MEDIUM = "medium"        # Degraded functionality
    LOW = "low"              # Minor issues, system works normally
    INFO = "info"            # Informational, not really an error


class ErrorCategory(Enum):
    """Error categories for better organization."""
    DATA_ACCESS = "data_access"        # API failures, network issues
    VALIDATION = "validation"          # Input validation errors
    CALCULATION = "calculation"        # Valuation model errors
    CONFIGURATION = "configuration"    # Setup/config issues
    SYSTEM = "system"                  # Infrastructure problems
    USER_INPUT = "user_input"          # User-provided data issues
    EXTERNAL_SERVICE = "external_service"  # Third-party service issues


@dataclass
class ErrorContext:
    """Context information for errors."""
    ticker: Optional[str] = None
    model: Optional[str] = None
    function_name: Optional[str] = None
    user_input: Optional[Dict[str, Any]] = None
    system_state: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ErrorInfo:
    """Comprehensive error information."""
    error_id: str
    exception: Exception
    severity: ErrorSeverity
    category: ErrorCategory
    user_message: str
    technical_message: str
    suggested_actions: List[str]
    context: ErrorContext
    recoverable: bool = True
    retry_possible: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/reporting."""
        return {
            "error_id": self.error_id,
            "exception_type": type(self.exception).__name__,
            "exception_message": str(self.exception),
            "severity": self.severity.value,
            "category": self.category.value,
            "user_message": self.user_message,
            "technical_message": self.technical_message,
            "suggested_actions": self.suggested_actions,
            "recoverable": self.recoverable,
            "retry_possible": self.retry_possible,
            "context": {
                "ticker": self.context.ticker,
                "model": self.context.model,
                "function_name": self.context.function_name,
                "timestamp": self.context.timestamp.isoformat()
            }
        }


class ErrorHandler:
    """Centralized error handling and recovery system."""

    def __init__(self):
        self.error_count = 0
        self.error_history: List[ErrorInfo] = []
        self.recovery_strategies: Dict[type, Callable] = {}
        self.max_history_size = 1000

        # Register default recovery strategies
        self._register_default_recovery_strategies()

    def handle_error(
        self,
        exception: Exception,
        context: Optional[ErrorContext] = None,
        custom_message: Optional[str] = None,
        suggested_actions: Optional[List[str]] = None
    ) -> ErrorInfo:
        """
        Handle an error with comprehensive information and recovery.

        Args:
            exception: The exception that occurred
            context: Context information about when/where the error occurred
            custom_message: Custom user-friendly message
            suggested_actions: Custom suggested actions for the user

        Returns:
            ErrorInfo object with comprehensive error details
        """
        self.error_count += 1
        error_id = f"ERR_{self.error_count:06d}_{int(datetime.now().timestamp())}"

        # Analyze the error
        severity, category = self._analyze_error(exception, context)
        user_message = custom_message or self._generate_user_message(exception, context)
        tech_message = self._generate_technical_message(exception, context)
        actions = suggested_actions or self._generate_suggested_actions(exception, context)

        # Create error info
        error_info = ErrorInfo(
            error_id=error_id,
            exception=exception,
            severity=severity,
            category=category,
            user_message=user_message,
            technical_message=tech_message,
            suggested_actions=actions,
            context=context or ErrorContext(),
            recoverable=self._is_recoverable(exception),
            retry_possible=self._is_retryable(exception)
        )

        # Log the error
        self._log_error(error_info)

        # Store in history
        self._store_error_history(error_info)

        # Attempt recovery if possible
        if error_info.recoverable:
            recovery_result = self._attempt_recovery(error_info)
            if recovery_result:
                logger.info(f"Successfully recovered from error {error_id}")

        return error_info

    def _analyze_error(self, exception: Exception, context: Optional[ErrorContext]) -> tuple:
        """Analyze error to determine severity and category."""

        # Determine severity
        if isinstance(exception, (SystemError, MemoryError, KeyboardInterrupt)):
            severity = ErrorSeverity.CRITICAL
        elif isinstance(exception, (DataFetchError, RateLimitError, ValuationError)):
            severity = ErrorSeverity.HIGH
        elif isinstance(exception, (ValidationError, ModelNotSuitableError)):
            severity = ErrorSeverity.MEDIUM
        elif isinstance(exception, InsufficientDataError):
            severity = ErrorSeverity.LOW
        else:
            severity = ErrorSeverity.MEDIUM

        # Determine category
        if isinstance(exception, (DataFetchError, RateLimitError)):
            category = ErrorCategory.DATA_ACCESS
        elif isinstance(exception, ValidationError):
            category = ErrorCategory.VALIDATION
        elif isinstance(exception, (ValuationError, ModelNotSuitableError)):
            category = ErrorCategory.CALCULATION
        elif isinstance(exception, AnalysisError):
            category = ErrorCategory.SYSTEM
        elif "network" in str(exception).lower() or "connection" in str(exception).lower():
            category = ErrorCategory.EXTERNAL_SERVICE
        else:
            category = ErrorCategory.SYSTEM

        return severity, category

    def _generate_user_message(self, exception: Exception, context: Optional[ErrorContext]) -> str:
        """Generate user-friendly error message."""

        if isinstance(exception, DataFetchError):
            if context and context.ticker:
                return f"Unable to retrieve data for {context.ticker}. This might be due to an invalid ticker symbol or temporary data provider issues."
            else:
                return "Unable to retrieve stock data. Please check your internet connection and try again."

        elif isinstance(exception, RateLimitError):
            return "Too many requests sent to the data provider. Please wait a moment and try again."

        elif isinstance(exception, ValidationError):
            return f"Invalid input provided: {exception}. Please check your data and try again."

        elif isinstance(exception, ModelNotSuitableError):
            if hasattr(exception, 'ticker') and hasattr(exception, 'model'):
                return f"The {exception.model} valuation model is not suitable for {exception.ticker} due to the company's characteristics."
            else:
                return "The selected valuation model is not suitable for this company."

        elif isinstance(exception, InsufficientDataError):
            return "Insufficient data available to complete the analysis. Some financial metrics may be missing."

        elif "timeout" in str(exception).lower():
            return "The request timed out. This might be due to network issues or high server load. Please try again."

        elif "network" in str(exception).lower() or "connection" in str(exception).lower():
            return "Network connection problem. Please check your internet connection and try again."

        else:
            return f"An unexpected error occurred during the analysis. Error details: {str(exception)[:100]}..."

    def _generate_technical_message(self, exception: Exception, context: Optional[ErrorContext]) -> str:
        """Generate technical error message for logging."""
        msg_parts = []

        if context:
            if context.ticker:
                msg_parts.append(f"Ticker: {context.ticker}")
            if context.model:
                msg_parts.append(f"Model: {context.model}")
            if context.function_name:
                msg_parts.append(f"Function: {context.function_name}")

        msg_parts.append(f"Exception: {type(exception).__name__}")
        msg_parts.append(f"Message: {str(exception)}")

        return " | ".join(msg_parts)

    def _generate_suggested_actions(self, exception: Exception, context: Optional[ErrorContext]) -> List[str]:
        """Generate suggested actions for the user."""

        if isinstance(exception, DataFetchError):
            return [
                "Verify the ticker symbol is correct",
                "Check your internet connection",
                "Try again in a few minutes",
                "Use a different ticker symbol for testing"
            ]

        elif isinstance(exception, RateLimitError):
            return [
                "Wait 60 seconds before trying again",
                "Reduce the number of stocks being analyzed at once",
                "Consider using the mock data provider for testing"
            ]

        elif isinstance(exception, ValidationError):
            return [
                "Check the input format and try again",
                "Refer to the documentation for valid input examples",
                "Use the validation tools to check your data"
            ]

        elif isinstance(exception, ModelNotSuitableError):
            return [
                "Try a different valuation model",
                "Check if the company has sufficient financial history",
                "Use the Simple Ratios model as a fallback"
            ]

        elif isinstance(exception, InsufficientDataError):
            return [
                "Try a different ticker symbol",
                "Use a more established company with complete financial data",
                "Check back later as data may become available"
            ]

        else:
            return [
                "Try the operation again",
                "Check the system logs for more details",
                "Contact support if the problem persists"
            ]

    def _is_recoverable(self, exception: Exception) -> bool:
        """Check if the error is recoverable."""
        non_recoverable = (SystemError, MemoryError, KeyboardInterrupt, SyntaxError)
        return not isinstance(exception, non_recoverable)

    def _is_retryable(self, exception: Exception) -> bool:
        """Check if the operation can be retried."""
        retryable_exceptions = (DataFetchError, RateLimitError, ConnectionError, TimeoutError)
        return isinstance(exception, retryable_exceptions)

    def _log_error(self, error_info: ErrorInfo):
        """Log the error with appropriate level."""
        extra_data = error_info.to_dict()

        if error_info.severity == ErrorSeverity.CRITICAL:
            logger.critical(error_info.user_message, extra=extra_data)
        elif error_info.severity == ErrorSeverity.HIGH:
            logger.error(error_info.user_message, extra=extra_data)
        elif error_info.severity == ErrorSeverity.MEDIUM:
            logger.warning(error_info.user_message, extra=extra_data)
        else:
            logger.info(error_info.user_message, extra=extra_data)

    def _store_error_history(self, error_info: ErrorInfo):
        """Store error in history with size management."""
        self.error_history.append(error_info)

        # Maintain history size
        if len(self.error_history) > self.max_history_size:
            self.error_history = self.error_history[-self.max_history_size:]

    def _register_default_recovery_strategies(self):
        """Register default recovery strategies for common errors."""

        def retry_with_backoff(error_info: ErrorInfo) -> bool:
            """Simple retry strategy with exponential backoff."""
            import random
            import time

            max_retries = 3
            base_delay = 1.0

            for attempt in range(max_retries):
                try:
                    delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    logger.info(f"Retrying operation after {delay:.1f}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)

                    # This would need to be implemented with actual retry logic
                    # For now, just return False to indicate no recovery
                    return False

                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"Retry failed after {max_retries} attempts: {e}")
                        return False

            return False

        # Register strategies
        self.recovery_strategies[DataFetchError] = retry_with_backoff
        self.recovery_strategies[RateLimitError] = retry_with_backoff
        self.recovery_strategies[ConnectionError] = retry_with_backoff

    def _attempt_recovery(self, error_info: ErrorInfo) -> bool:
        """Attempt to recover from the error using registered strategies."""
        exception_type = type(error_info.exception)

        if exception_type in self.recovery_strategies:
            try:
                return self.recovery_strategies[exception_type](error_info)
            except Exception as e:
                logger.error(f"Recovery strategy failed: {e}")

        return False

    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get error summary for the specified time period."""
        from datetime import timedelta

        cutoff_time = datetime.now() - timedelta(hours=hours)
        recent_errors = [
            err for err in self.error_history
            if err.context.timestamp > cutoff_time
        ]

        # Categorize errors
        by_severity = {}
        by_category = {}
        by_ticker = {}

        for error in recent_errors:
            # By severity
            severity_key = error.severity.value
            by_severity[severity_key] = by_severity.get(severity_key, 0) + 1

            # By category
            category_key = error.category.value
            by_category[category_key] = by_category.get(category_key, 0) + 1

            # By ticker
            if error.context.ticker:
                ticker = error.context.ticker
                by_ticker[ticker] = by_ticker.get(ticker, 0) + 1

        return {
            "time_period_hours": hours,
            "total_errors": len(recent_errors),
            "by_severity": by_severity,
            "by_category": by_category,
            "top_problematic_tickers": dict(sorted(by_ticker.items(), key=lambda x: x[1], reverse=True)[:10]),
            "most_recent_errors": [err.to_dict() for err in recent_errors[-5:]]
        }

    def clear_history(self):
        """Clear error history."""
        self.error_history.clear()
        self.error_count = 0
        logger.info("Error history cleared")


# Global error handler instance
error_handler = ErrorHandler()


# Decorator for automatic error handling
def handle_errors(
    custom_message: Optional[str] = None,
    suggested_actions: Optional[List[str]] = None,
    reraise: bool = False
):
    """
    Decorator for automatic error handling in functions.

    Args:
        custom_message: Custom user-friendly error message
        suggested_actions: Custom suggested actions
        reraise: Whether to reraise the exception after handling
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                context = ErrorContext(
                    function_name=func.__name__,
                    user_input={"args": str(args)[:200], "kwargs": str(kwargs)[:200]}
                )

                error_handler.handle_error(
                    exception=e,
                    context=context,
                    custom_message=custom_message,
                    suggested_actions=suggested_actions
                )

                if reraise:
                    raise e
                else:
                    return None  # Graceful degradation

        return wrapper
    return decorator


# Context manager for error handling
class ErrorHandlingContext:
    """Context manager for handling errors in code blocks."""

    def __init__(self, context: ErrorContext, reraise: bool = True):
        self.context = context
        self.reraise = reraise
        self.error_info: Optional[ErrorInfo] = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.error_info = error_handler.handle_error(
                exception=exc_val,
                context=self.context
            )

            if not self.reraise:
                return True  # Suppress the exception

        return False  # Let the exception propagate


# Convenience functions
def handle_error(exception: Exception, **kwargs) -> ErrorInfo:
    """Convenience function to handle a single error."""
    return error_handler.handle_error(exception, **kwargs)


def get_error_summary(hours: int = 24) -> Dict[str, Any]:
    """Convenience function to get error summary."""
    return error_handler.get_error_summary(hours)


def create_error_context(ticker: str = None, model: str = None, **kwargs) -> ErrorContext:
    """Convenience function to create error context."""
    return ErrorContext(ticker=ticker, model=model, **kwargs)
