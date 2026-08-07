"""
Input validation utilities for the investment analysis system.

This module provides validation functions to ensure data integrity
and catch errors early in the analysis pipeline.
"""

import re
from typing import Any, Dict, List

from .exceptions import ValidationError, raise_ticker_validation_error


def validate_ticker(ticker: str) -> str:
    """
    Validate and normalize ticker symbol.

    Args:
        ticker: Stock ticker symbol to validate

    Returns:
        Normalized ticker symbol (uppercase, stripped)

    Raises:
        ValidationError: If ticker format is invalid
    """
    if not ticker or not isinstance(ticker, str):
        raise_ticker_validation_error(ticker, "Ticker must be a non-empty string")

    # Normalize ticker
    ticker = ticker.upper().strip()

    # Basic ticker format validation
    # Allows: A-Z (1-5 chars), optional suffix like -A, -B, etc.
    if not re.match(r'^[A-Z]{1,5}(-[A-Z])?$', ticker):
        raise_ticker_validation_error(
            ticker,
            "Invalid ticker format. Expected 1-5 letters, optional suffix (e.g., BRK-A)"
        )

    return ticker


def validate_ticker_list(tickers: List[str]) -> List[str]:
    """
    Validate and normalize a list of ticker symbols.

    Args:
        tickers: List of ticker symbols

    Returns:
        List of normalized ticker symbols

    Raises:
        ValidationError: If any ticker is invalid
    """
    if not isinstance(tickers, list):
        raise ValidationError("tickers", str(tickers), "Must be a list")

    if not tickers:
        raise ValidationError("tickers", "[]", "Cannot be empty")

    validated_tickers = []
    for ticker in tickers:
        validated_tickers.append(validate_ticker(ticker))

    return validated_tickers


def validate_positive_number(value: Any, field_name: str, allow_zero: bool = False) -> float:
    """
    Validate that a value is a positive number.

    Args:
        value: Value to validate
        field_name: Name of the field for error messages
        allow_zero: Whether to allow zero values

    Returns:
        Validated float value

    Raises:
        ValidationError: If value is not a positive number
    """
    try:
        float_value = float(value)
    except (ValueError, TypeError):
        raise ValidationError(field_name, str(value), "Must be a number")

    if float_value < 0:
        raise ValidationError(field_name, str(value), "Must be positive")

    if not allow_zero and float_value == 0:
        raise ValidationError(field_name, str(value), "Must be greater than zero")

    return float_value


def validate_percentage(value: Any, field_name: str, min_pct: float = 0.0, max_pct: float = 1.0) -> float:
    """
    Validate that a value is a valid percentage (0-1 decimal format).

    Args:
        value: Value to validate
        field_name: Name of the field for error messages
        min_pct: Minimum allowed percentage (default 0.0)
        max_pct: Maximum allowed percentage (default 1.0)

    Returns:
        Validated percentage as decimal

    Raises:
        ValidationError: If value is not a valid percentage
    """
    float_value = validate_positive_number(value, field_name, allow_zero=True)

    if float_value < min_pct or float_value > max_pct:
        raise ValidationError(
            field_name,
            str(value),
            f"Must be between {min_pct:.1%} and {max_pct:.1%}"
        )

    return float_value


def validate_integer_range(value: Any, field_name: str, min_val: int, max_val: int) -> int:
    """
    Validate that a value is an integer within specified range.

    Args:
        value: Value to validate
        field_name: Name of the field for error messages
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)

    Returns:
        Validated integer value

    Raises:
        ValidationError: If value is not a valid integer in range
    """
    try:
        int_value = int(value)
    except (ValueError, TypeError):
        raise ValidationError(field_name, str(value), "Must be an integer")

    if int_value < min_val or int_value > max_val:
        raise ValidationError(
            field_name,
            str(value),
            f"Must be between {min_val} and {max_val}"
        )

    return int_value


def validate_financial_data(data: Dict[str, Any], required_fields: List[str]) -> Dict[str, Any]:
    """
    Validate that financial data contains required fields with valid values.

    Args:
        data: Dictionary of financial data
        required_fields: List of required field names

    Returns:
        Validated financial data dictionary

    Raises:
        ValidationError: If required fields are missing or invalid
    """
    if not isinstance(data, dict):
        raise ValidationError("financial_data", str(data), "Must be a dictionary")

    missing_fields = [field for field in required_fields if field not in data or data[field] is None]

    if missing_fields:
        raise ValidationError(
            "financial_data",
            str(data.keys()),
            f"Missing required fields: {', '.join(missing_fields)}"
        )

    # Validate numeric fields are actually numeric
    for field in required_fields:
        value = data[field]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            continue  # Valid numeric value

        try:
            float(value)
        except (ValueError, TypeError):
            raise ValidationError(
                f"financial_data.{field}",
                str(value),
                "Must be a numeric value"
            )

    return data


def validate_config_dict(config: Dict[str, Any], schema: Dict[str, type]) -> Dict[str, Any]:
    """
    Validate configuration dictionary against a schema.

    Args:
        config: Configuration dictionary to validate
        schema: Dictionary mapping field names to expected types

    Returns:
        Validated configuration dictionary

    Raises:
        ValidationError: If configuration doesn't match schema
    """
    if not isinstance(config, dict):
        raise ValidationError("config", str(config), "Must be a dictionary")

    for field, expected_type in schema.items():
        if field not in config:
            raise ValidationError("config", str(config.keys()), f"Missing required field: {field}")

        value = config[field]
        if not isinstance(value, expected_type):
            raise ValidationError(
                f"config.{field}",
                str(value),
                f"Must be of type {expected_type.__name__}"
            )

    return config


# Convenience validation functions for common use cases

def is_valid_ticker_format(ticker: str) -> bool:
    """Check if ticker has valid format without raising exception."""
    try:
        validate_ticker(ticker)
        return True
    except ValidationError:
        return False


def sanitize_ticker_list(tickers: List[str]) -> List[str]:
    """Remove invalid tickers from list and return only valid ones."""
    valid_tickers = []
    for ticker in tickers:
        try:
            valid_tickers.append(validate_ticker(ticker))
        except ValidationError:
            continue  # Skip invalid tickers
    return valid_tickers
