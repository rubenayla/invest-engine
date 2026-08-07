"""
Type validation utilities for backtesting system.
"""

import logging
from functools import wraps
from typing import Any, Callable, Dict, TypeVar, Union

import pandas as pd

logger = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])


def ensure_python_types(func: F) -> F:
    """
    Decorator to ensure function returns Python primitives, not pandas objects.

    Converts pandas Series/DataFrame scalars to Python float/int/str.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)

        if isinstance(result, dict):
            # Convert dictionary values
            return {k: _convert_to_python_type(v) for k, v in result.items()}
        else:
            # Convert single value
            return _convert_to_python_type(result)

    return wrapper


def _convert_to_python_type(value: Any) -> Union[float, int, str, bool, None, Any]:
    """Convert pandas objects to Python primitives."""
    if pd.isna(value):
        return None
    elif hasattr(value, 'dtype') and hasattr(value, 'item'):
        # pandas scalar (Series with single value, numpy scalar)
        try:
            return value.item()
        except (ValueError, AttributeError):
            pass
    elif isinstance(value, (pd.Series, pd.DataFrame)):
        if len(value) == 0:
            return None if isinstance(value, pd.Series) else {}
        elif len(value) == 1:
            if isinstance(value, pd.Series):
                return _convert_to_python_type(value.iloc[0])
            else:
                return _convert_to_python_type(value.iloc[0, 0])
        else:
            logger.warning(f"Cannot convert pandas object with length {len(value)} to scalar")
            return value

    # Already a Python type or unknown type
    return value


def validate_price_dict(prices: Dict[str, Any]) -> Dict[str, float]:
    """
    Validate and convert price dictionary to ensure all values are Python floats.

    Parameters
    ----------
    prices : Dict[str, Any]
        Dictionary that should contain ticker -> price mappings

    Returns
    -------
    Dict[str, float]
        Validated dictionary with Python float values

    Raises
    ------
    TypeError
        If any price cannot be converted to float
    """
    validated: Dict[str, float] = {}

    for ticker, price in prices.items():
        try:
            if pd.isna(price):
                logger.warning(f"Price for {ticker} is NaN, skipping")
                continue

            # Convert pandas objects to Python float
            if hasattr(price, 'item'):
                validated[ticker] = float(price.item())
            elif isinstance(price, (pd.Series, pd.DataFrame)):
                if len(price) > 0:
                    validated[ticker] = float(price.iloc[0])
                else:
                    logger.warning(f"Empty price data for {ticker}, skipping")
                    continue
            else:
                validated[ticker] = float(price)

        except (ValueError, TypeError) as e:
            logger.error(f"Cannot convert price for {ticker} to float: {price} ({type(price)}) - {e}")
            raise TypeError(f"Invalid price data for {ticker}: {price}")

    return validated
