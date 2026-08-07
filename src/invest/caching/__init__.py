"""
Caching Layer for Investment Analysis System

This package provides efficient caching mechanisms for API responses,
financial data, and computation results to improve performance and
reduce external API calls.
"""

from .cache_backends import FileCache, MemoryCache, RedisCache
from .cache_decorators import cached_api_call, cached_computation
from .cache_manager import CacheManager

# Export main interfaces
__all__ = [
    'CacheManager',
    'MemoryCache',
    'FileCache',
    'RedisCache',
    'cached_api_call',
    'cached_computation',
]
