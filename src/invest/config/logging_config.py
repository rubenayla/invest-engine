"""
Structured logging configuration for the investment analysis system.

This module sets up consistent logging across all components with proper
formatting, levels, and structured data support for better debugging.
"""

import logging
import logging.config
import sys
from pathlib import Path
from typing import Any, Dict


def setup_logging(
    level: str = "INFO",
    log_to_file: bool = True,
    log_file_path: str = "logs/investment_analysis.log",
    enable_structured_logging: bool = True
) -> None:
    """
    Configure logging for the investment analysis system.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
        log_to_file: Whether to write logs to file
        log_file_path: Path to log file
        enable_structured_logging: Whether to use structured JSON logging
    """

    # Create logs directory if it doesn't exist
    if log_to_file:
        log_path = Path(log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Configure logging
    config = get_logging_config(level, log_to_file, log_file_path, enable_structured_logging)
    logging.config.dictConfig(config)

    # Set up specific loggers for external libraries to reduce noise
    logging.getLogger("yfinance").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logging_config(
    level: str,
    log_to_file: bool,
    log_file_path: str,
    enable_structured_logging: bool
) -> Dict[str, Any]:
    """Get logging configuration dictionary."""

    # Formatters
    formatters = {
        "standard": {
            "format": "%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        },
        "detailed": {
            "format": "%(asctime)s [%(levelname)8s] %(name)s:%(lineno)d - %(funcName)s(): %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S"
        }
    }

    if enable_structured_logging:
        formatters["structured"] = {
            "()": StructuredFormatter,
            "datefmt": "%Y-%m-%d %H:%M:%S"
        }

    # Handlers
    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "level": level,
            "formatter": "standard",
            "stream": sys.stdout
        }
    }

    if log_to_file:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": log_file_path,
            "maxBytes": 10485760,  # 10MB
            "backupCount": 5
        }

        if enable_structured_logging:
            handlers["structured_file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "structured",
                "filename": log_file_path.replace('.log', '_structured.log'),
                "maxBytes": 10485760,  # 10MB
                "backupCount": 5
            }

    # Root logger configuration
    root_handlers = ["console"]
    if log_to_file:
        root_handlers.extend(["file", "structured_file"] if enable_structured_logging else ["file"])

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "handlers": handlers,
        "root": {
            "level": "DEBUG",
            "handlers": root_handlers
        },
        "loggers": {
            "invest": {
                "level": level,
                "handlers": root_handlers,
                "propagate": False
            }
        }
    }


class StructuredFormatter(logging.Formatter):
    """
    Custom formatter that outputs structured JSON logs.

    This enables better log analysis and monitoring in production.
    """

    def format(self, record):
        import json
        from datetime import datetime

        # Base log structure
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage()
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": self.formatException(record.exc_info) if record.exc_info else None
            }

        # Add any extra fields that were passed to the log call
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'levelname', 'levelno', 'pathname',
                          'filename', 'module', 'lineno', 'funcName', 'created', 'msecs',
                          'relativeCreated', 'thread', 'threadName', 'processName', 'process',
                          'getMessage', 'exc_info', 'exc_text', 'stack_info']:
                log_entry["extra"] = log_entry.get("extra", {})
                log_entry["extra"][key] = value

        return json.dumps(log_entry)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(f"invest.{name}")


# Convenience functions for common logging patterns

def log_function_call(logger: logging.Logger, func_name: str, **kwargs):
    """Log a function call with parameters."""
    logger.debug(f"Calling {func_name}", extra={"function_call": func_name, "parameters": kwargs})


def log_data_fetch(logger: logging.Logger, ticker: str, data_type: str, success: bool, **kwargs):
    """Log data fetching operations."""
    level = logging.INFO if success else logging.WARNING
    logger.log(
        level,
        f"Data fetch {'succeeded' if success else 'failed'} for {ticker}",
        extra={
            "operation": "data_fetch",
            "ticker": ticker,
            "data_type": data_type,
            "success": success,
            **kwargs
        }
    )


def log_valuation_result(logger: logging.Logger, ticker: str, model: str, fair_value: float, **kwargs):
    """Log valuation calculation results."""
    logger.info(
        f"Valuation complete for {ticker}",
        extra={
            "operation": "valuation",
            "ticker": ticker,
            "model": model,
            "fair_value": fair_value,
            **kwargs
        }
    )


def log_performance_metric(logger: logging.Logger, operation: str, duration_seconds: float, **kwargs):
    """Log performance metrics."""
    logger.info(
        f"Performance: {operation} completed in {duration_seconds:.2f}s",
        extra={
            "operation": "performance",
            "metric_type": operation,
            "duration_seconds": duration_seconds,
            **kwargs
        }
    )


def log_error_with_context(logger: logging.Logger, error: Exception, context: Dict[str, Any]):
    """Log errors with additional context."""
    logger.error(
        f"Error occurred: {error}",
        extra={
            "operation": "error",
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context
        },
        exc_info=True
    )
