"""
Cache Decorators - Function decorators for automatic caching.

This module provides decorators that can be applied to functions to
automatically cache their results based on function arguments.
"""

import functools
import hashlib
import json
import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

from .cache_manager import CacheKey, get_cache_manager

logger = logging.getLogger(__name__)


def cached_api_call(data_type: str = 'default',
                   ttl: Optional[int] = None,
                   key_prefix: str = '',
                   skip_cache: bool = False):
    """
    Decorator for caching API call results.

    Parameters
    ----------
    data_type : str
        Type of data being cached (affects backend and TTL)
    ttl : Optional[int]
        Custom TTL in seconds, overrides default for data type
    key_prefix : str
        Prefix to add to generated cache keys
    skip_cache : bool
        If True, skip caching (useful for debugging)

    Usage
    -----
    @cached_api_call(data_type='stock_info', ttl=3600)
    def get_stock_info(ticker: str) -> dict:
        # Expensive API call
        return fetch_from_api(ticker)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if skip_cache:
                return func(*args, **kwargs)

            cache_manager = get_cache_manager()

            # Generate cache key from function name and arguments
            cache_key = _generate_function_cache_key(func, args, kwargs, key_prefix)

            # Try to get from cache first
            cached_result = cache_manager.get(cache_key, data_type)
            if cached_result is not None:
                logger.debug(f"Cache hit for {func.__name__} with key: {cache_key}")
                return cached_result

            # Cache miss - execute function
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time

                # Cache the result if it's not None
                if result is not None:
                    cache_manager.set(cache_key, result, data_type, ttl)
                    logger.debug(f"Cached result for {func.__name__} (exec: {execution_time:.2f}s)")

                return result

            except Exception as e:
                execution_time = time.time() - start_time
                logger.warning(f"Function {func.__name__} failed after {execution_time:.2f}s: {e}")
                raise

        # Add cache control methods to the function
        wrapper.cache_invalidate = lambda *args, **kwargs: _invalidate_function_cache(
            func, args, kwargs, key_prefix, data_type
        )
        wrapper.cache_key = lambda *args, **kwargs: _generate_function_cache_key(
            func, args, kwargs, key_prefix
        )

        return wrapper

    return decorator


def cached_computation(ttl: int = 3600,
                      key_prefix: str = '',
                      skip_cache: bool = False):
    """
    Decorator for caching expensive computation results.

    Parameters
    ----------
    ttl : int
        Cache TTL in seconds
    key_prefix : str
        Prefix to add to generated cache keys
    skip_cache : bool
        If True, skip caching (useful for debugging)

    Usage
    -----
    @cached_computation(ttl=1800)  # 30 minutes
    def calculate_complex_metric(ticker: str, params: dict) -> float:
        # Expensive computation
        return compute_result(ticker, params)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if skip_cache:
                return func(*args, **kwargs)

            cache_manager = get_cache_manager()

            # Generate cache key
            cache_key = _generate_function_cache_key(func, args, kwargs, key_prefix)

            # Try cache first
            cached_result = cache_manager.get(cache_key, 'computation')
            if cached_result is not None:
                logger.debug(f"Computation cache hit for {func.__name__}")
                return cached_result

            # Execute computation
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time

                # Cache the result
                if result is not None:
                    cache_manager.set(cache_key, result, 'computation', ttl)
                    logger.debug(f"Cached computation result for {func.__name__} (exec: {execution_time:.2f}s)")

                return result

            except Exception as e:
                execution_time = time.time() - start_time
                logger.warning(f"Computation {func.__name__} failed after {execution_time:.2f}s: {e}")
                raise

        # Add cache control methods
        wrapper.cache_invalidate = lambda *args, **kwargs: _invalidate_function_cache(
            func, args, kwargs, key_prefix, 'computation'
        )
        wrapper.cache_key = lambda *args, **kwargs: _generate_function_cache_key(
            func, args, kwargs, key_prefix
        )

        return wrapper

    return decorator


def cache_result_by_ticker(data_type: str, ttl: Optional[int] = None):
    """
    Specialized decorator for functions that take a ticker as first argument.

    This decorator automatically generates cache keys based on the ticker symbol
    and uses the appropriate caching strategy for financial data.

    Parameters
    ----------
    data_type : str
        Type of financial data ('stock_info', 'financials', 'valuation', etc.)
    ttl : Optional[int]
        Custom TTL in seconds

    Usage
    -----
    @cache_result_by_ticker('stock_info', ttl=86400)
    def get_stock_info(ticker: str) -> dict:
        return fetch_stock_info(ticker)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(ticker: str, *args, **kwargs):
            cache_manager = get_cache_manager()

            # Generate ticker-based cache key
            base_key = _get_ticker_cache_key(data_type, ticker, func.__name__)

            # Add additional args/kwargs to key if present
            if args or kwargs:
                arg_hash = _hash_args_kwargs(args, kwargs)
                cache_key = f"{base_key}:{arg_hash}"
            else:
                cache_key = base_key

            # Try cache first
            cached_result = cache_manager.get(cache_key, data_type)
            if cached_result is not None:
                logger.debug(f"Ticker cache hit for {func.__name__}({ticker})")
                return cached_result

            # Execute function
            start_time = time.time()
            try:
                result = func(ticker, *args, **kwargs)
                execution_time = time.time() - start_time

                # Cache the result
                if result is not None:
                    cache_manager.set(cache_key, result, data_type, ttl)
                    logger.debug(f"Cached {data_type} for {ticker} (exec: {execution_time:.2f}s)")

                return result

            except Exception as e:
                execution_time = time.time() - start_time
                logger.warning(f"Function {func.__name__}({ticker}) failed after {execution_time:.2f}s: {e}")
                raise

        # Add cache control methods
        wrapper.cache_invalidate = lambda ticker, *args, **kwargs: _invalidate_ticker_cache(
            data_type, ticker, func.__name__, args, kwargs
        )

        return wrapper

    return decorator


def _generate_function_cache_key(func: Callable, args: Tuple, kwargs: Dict,
                                prefix: str = '') -> str:
    """Generate a cache key for a function call."""
    # Create base key from function name
    base_key = f"{prefix}{func.__module__}.{func.__name__}" if prefix else f"{func.__module__}.{func.__name__}"

    # Hash arguments to create unique key
    if args or kwargs:
        arg_hash = _hash_args_kwargs(args, kwargs)
        return f"{base_key}:{arg_hash}"
    else:
        return base_key


def _hash_args_kwargs(args: Tuple, kwargs: Dict) -> str:
    """Create a hash from function arguments."""
    try:
        # Create a deterministic representation
        arg_data = {
            'args': args,
            'kwargs': sorted(kwargs.items()) if kwargs else {}
        }

        # Convert to JSON string for hashing (handles most data types)
        arg_json = json.dumps(arg_data, sort_keys=True, default=str)

        # Create hash
        return hashlib.md5(arg_json.encode()).hexdigest()[:16]  # Use first 16 chars

    except (TypeError, ValueError):
        # Fallback for non-serializable objects
        arg_str = f"{str(args)}{str(kwargs)}"
        return hashlib.md5(arg_str.encode()).hexdigest()[:16]


def _get_ticker_cache_key(data_type: str, ticker: str, func_name: str) -> str:
    """Generate a cache key for ticker-based data."""
    ticker = ticker.upper()

    if data_type == 'stock_info':
        return CacheKey.stock_info(ticker)
    elif data_type == 'financials':
        return CacheKey.financials(ticker, func_name)
    elif data_type == 'valuation':
        return CacheKey.valuation(ticker, func_name)
    elif data_type == 'market_data':
        return CacheKey.market_data(ticker, func_name)
    else:
        return f"{data_type}:{ticker}:{func_name}"


def _invalidate_function_cache(func: Callable, args: Tuple, kwargs: Dict,
                              prefix: str, data_type: str) -> bool:
    """Invalidate cache for a specific function call."""
    cache_manager = get_cache_manager()
    cache_key = _generate_function_cache_key(func, args, kwargs, prefix)
    return cache_manager.delete(cache_key, data_type)


def _invalidate_ticker_cache(data_type: str, ticker: str, func_name: str,
                            args: Tuple, kwargs: Dict) -> bool:
    """Invalidate cache for a ticker-based function call."""
    cache_manager = get_cache_manager()

    base_key = _get_ticker_cache_key(data_type, ticker, func_name)

    if args or kwargs:
        arg_hash = _hash_args_kwargs(args, kwargs)
        cache_key = f"{base_key}:{arg_hash}"
    else:
        cache_key = base_key

    return cache_manager.delete(cache_key, data_type)


# Utility functions for manual cache control

def invalidate_all_ticker_cache(ticker: str) -> None:
    """Invalidate all cached data for a ticker."""
    cache_manager = get_cache_manager()
    cache_manager.invalidate_ticker(ticker)


def get_cache_stats() -> Dict[str, Any]:
    """Get comprehensive cache statistics."""
    cache_manager = get_cache_manager()
    return cache_manager.get_stats()


def clear_all_caches() -> None:
    """Clear all caches."""
    cache_manager = get_cache_manager()
    cache_manager.clear_all()


def cleanup_expired_cache() -> None:
    """Clean up expired cache entries."""
    cache_manager = get_cache_manager()
    cache_manager.cleanup()
