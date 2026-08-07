"""
Comprehensive error handling system for the investment analysis framework.

This package provides centralized error handling, recovery strategies, and
user-friendly error management to improve system reliability and user experience.

Usage:
    # Basic error handling
    from src.invest.error_handling import handle_error, create_error_context

    try:
        # Some operation that might fail
        result = risky_operation()
    except Exception as e:
        context = create_error_context(ticker="AAPL", model="dcf")
        error_info = handle_error(e, context=context)
        print(f"User message: {error_info.user_message}")
        print(f"Suggested actions: {error_info.suggested_actions}")

    # Using decorator for automatic error handling
    from src.invest.error_handling import handle_errors

    @handle_errors(custom_message="DCF calculation failed")
    def calculate_dcf_with_error_handling(ticker):
        return calculate_dcf(ticker)

    # Using context manager
    from src.invest.error_handling import ErrorHandlingContext, create_error_context

    context = create_error_context(ticker="AAPL", model="dcf")
    with ErrorHandlingContext(context, reraise=False) as error_ctx:
        result = risky_operation()
        if error_ctx.error_info:
            print(f"Error handled: {error_ctx.error_info.user_message}")
"""

from ..config.logging_config import get_logger
from .error_manager import (
    ErrorCategory,
    ErrorContext,
    ErrorHandler,
    ErrorHandlingContext,
    ErrorInfo,
    ErrorSeverity,
    create_error_context,
    error_handler,
    get_error_summary,
    handle_error,
    handle_errors,
)
from .recovery_strategies import (
    FallbackDataStrategy,
    GracefulDegradationStrategy,
    ModelSubstitutionStrategy,
    RecoveryManager,
    RecoveryStrategy,
    RetryWithBackoffStrategy,
    SystemHealthStrategy,
    UserGuidanceStrategy,
    recovery_manager,
)

logger = get_logger(__name__)


def setup_error_handling(enable_recovery: bool = True):
    """
    Setup comprehensive error handling for the application.

    Args:
        enable_recovery: Whether to enable automatic error recovery
    """
    logger.info("Setting up comprehensive error handling system")

    if enable_recovery:
        # Integrate recovery manager with error handler
        original_handle_error = error_handler.handle_error

        def enhanced_handle_error(exception, context=None, **kwargs):
            """Enhanced error handler with recovery attempts."""
            error_info = original_handle_error(exception, context, **kwargs)

            # Attempt recovery
            if error_info.recoverable:
                successful_strategies = recovery_manager.attempt_recovery(error_info)
                if successful_strategies:
                    logger.info(
                        f"Recovery attempted for {error_info.error_id}",
                        extra={"successful_strategies": successful_strategies}
                    )

            return error_info

        # Replace the handle_error method
        error_handler.handle_error = enhanced_handle_error
        logger.info("Error recovery system enabled")

    # Log setup completion
    logger.info("Error handling system setup complete")


def get_system_health_report() -> dict:
    """Get comprehensive system health report including error patterns."""
    error_summary = get_error_summary(hours=24)
    recovery_stats = recovery_manager.get_strategy_statistics()

    return {
        "timestamp": error_handler.error_history[-1].context.timestamp.isoformat() if error_handler.error_history else None,
        "error_summary": error_summary,
        "recovery_statistics": recovery_stats,
        "total_errors_handled": error_handler.error_count,
        "system_status": "healthy" if error_summary["total_errors"] < 10 else "degraded"
    }


# Convenience functions for common error scenarios

def handle_data_fetch_error(exception: Exception, ticker: str) -> ErrorInfo:
    """Handle data fetching errors with ticker context."""
    context = create_error_context(ticker=ticker, function_name="data_fetch")
    return handle_error(exception, context=context)


def handle_valuation_error(exception: Exception, ticker: str, model: str) -> ErrorInfo:
    """Handle valuation errors with model and ticker context."""
    context = create_error_context(ticker=ticker, model=model, function_name="valuation")
    return handle_error(exception, context=context)


def handle_validation_error(exception: Exception, user_input: dict) -> ErrorInfo:
    """Handle validation errors with user input context."""
    context = ErrorContext(
        function_name="validation",
        user_input=user_input
    )
    return handle_error(exception, context=context)


# Auto-setup error handling when module is imported
try:
    setup_error_handling(enable_recovery=True)
except Exception as e:
    # Fallback: basic setup without recovery
    logger.warning(f"Failed to setup enhanced error handling: {e}")
    setup_error_handling(enable_recovery=False)


__all__ = [
    # Core classes
    'ErrorHandler', 'ErrorInfo', 'ErrorContext', 'ErrorSeverity', 'ErrorCategory',
    'RecoveryStrategy', 'RecoveryManager',

    # Global instances
    'error_handler', 'recovery_manager',

    # Core functions
    'handle_error', 'get_error_summary', 'create_error_context',

    # Decorators and context managers
    'handle_errors', 'ErrorHandlingContext',

    # Setup and reporting
    'setup_error_handling', 'get_system_health_report',

    # Convenience functions
    'handle_data_fetch_error', 'handle_valuation_error', 'handle_validation_error',

    # Recovery strategies
    'RetryWithBackoffStrategy', 'FallbackDataStrategy', 'ModelSubstitutionStrategy',
    'GracefulDegradationStrategy', 'UserGuidanceStrategy', 'SystemHealthStrategy'
]
