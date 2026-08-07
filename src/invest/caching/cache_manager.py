"""
Cache Manager - Centralized cache management and coordination.

This module provides a high-level interface for managing different cache backends,
cache policies, and cache invalidation strategies across the investment system.
"""

import logging
from threading import RLock
from typing import Any, Dict, List, Optional

from ..config.constants import DATA_PROVIDER_CONFIG
from .cache_backends import CacheBackend, FileCache, MemoryCache

logger = logging.getLogger(__name__)


class CacheKey:
    """Utility class for generating consistent cache keys."""

    @staticmethod
    def stock_info(ticker: str) -> str:
        """Generate cache key for stock info data."""
        return f"stock_info:{ticker.upper()}"

    @staticmethod
    def financials(ticker: str, statement_type: str) -> str:
        """Generate cache key for financial statements."""
        return f"financials:{ticker.upper()}:{statement_type}"

    @staticmethod
    def valuation(ticker: str, model: str) -> str:
        """Generate cache key for valuation results."""
        return f"valuation:{ticker.upper()}:{model}"

    @staticmethod
    def market_data(ticker: str, data_type: str) -> str:
        """Generate cache key for market data."""
        return f"market_data:{ticker.upper()}:{data_type}"

    @staticmethod
    def screening_result(config_hash: str) -> str:
        """Generate cache key for screening results."""
        return f"screening:{config_hash}"

    @staticmethod
    def sp500_tickers() -> str:
        """Generate cache key for S&P 500 ticker list."""
        return "sp500_tickers"


class CachePolicy:
    """Cache policy configuration for different data types."""

    # Cache TTL settings (in seconds)
    STOCK_INFO_TTL = DATA_PROVIDER_CONFIG.CACHE_EXPIRY_HOURS * 3600  # 24 hours
    FINANCIALS_TTL = 6 * 3600  # 6 hours (updated quarterly)
    VALUATION_TTL = 2 * 3600  # 2 hours (market dependent)
    MARKET_DATA_TTL = 5 * 60  # 5 minutes (real-time data)
    SCREENING_TTL = 1 * 3600  # 1 hour
    SP500_TICKERS_TTL = 24 * 3600  # 24 hours

    # Cache backends for different data types
    BACKENDS = {
        'stock_info': 'file',  # Persistent for historical data
        'financials': 'file',  # Persistent for quarterly data
        'valuation': 'memory', # Fast access for calculations
        'market_data': 'memory', # Fast access for real-time data
        'screening': 'file',   # Persistent for expensive computations
    }


class CacheManager:
    """
    Central cache manager that coordinates multiple cache backends
    and implements intelligent caching strategies.
    """

    def __init__(self,
                 memory_cache_size: int = 1000,
                 file_cache_dir: str = ".cache",
                 enable_redis: bool = False,
                 redis_config: Optional[Dict[str, Any]] = None):
        """
        Initialize cache manager with multiple backends.

        Parameters
        ----------
        memory_cache_size : int
            Maximum items in memory cache
        file_cache_dir : str
            Directory for persistent file cache
        enable_redis : bool
            Whether to enable Redis backend
        redis_config : Optional[Dict[str, Any]]
            Redis configuration parameters
        """
        self.policy = CachePolicy()
        self._lock = RLock()

        # Initialize cache backends
        self.backends: Dict[str, CacheBackend] = {}

        # Always initialize memory and file caches
        self.backends['memory'] = MemoryCache(
            max_size=memory_cache_size,
            default_ttl=3600
        )

        self.backends['file'] = FileCache(
            cache_dir=file_cache_dir,
            default_ttl=86400
        )

        # Optionally initialize Redis cache
        if enable_redis:
            try:
                from .cache_backends import RedisCache
                redis_config = redis_config or {}
                self.backends['redis'] = RedisCache(**redis_config)
                logger.info("Redis cache backend initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Redis cache: {e}")

        # Statistics
        self._cache_stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'invalidations': 0
        }

        logger.info(f"Cache manager initialized with backends: {list(self.backends.keys())}")

    def get(self, key: str, data_type: str = 'default') -> Optional[Any]:
        """
        Get value from appropriate cache backend.

        Parameters
        ----------
        key : str
            Cache key
        data_type : str
            Type of data to determine cache backend and TTL

        Returns
        -------
        Optional[Any]
            Cached value or None if not found/expired
        """
        backend_name = self._get_backend_for_data_type(data_type)
        backend = self.backends.get(backend_name)

        if not backend:
            self._cache_stats['misses'] += 1
            return None

        with self._lock:
            value = backend.get(key)

            if value is not None:
                self._cache_stats['hits'] += 1
                logger.debug(f"Cache hit for key: {key} (backend: {backend_name})")
            else:
                self._cache_stats['misses'] += 1
                logger.debug(f"Cache miss for key: {key} (backend: {backend_name})")

            return value

    def set(self, key: str, value: Any, data_type: str = 'default',
            ttl: Optional[int] = None) -> None:
        """
        Set value in appropriate cache backend.

        Parameters
        ----------
        key : str
            Cache key
        value : Any
            Value to cache
        data_type : str
            Type of data to determine cache backend and TTL
        ttl : Optional[int]
            Custom TTL in seconds, overrides default for data type
        """
        backend_name = self._get_backend_for_data_type(data_type)
        backend = self.backends.get(backend_name)

        if not backend:
            logger.warning(f"No backend available for data type: {data_type}")
            return

        if ttl is None:
            ttl = self._get_ttl_for_data_type(data_type)

        with self._lock:
            backend.set(key, value, ttl)
            self._cache_stats['sets'] += 1
            logger.debug(f"Cache set for key: {key} (backend: {backend_name}, ttl: {ttl}s)")

    def delete(self, key: str, data_type: str = 'default') -> bool:
        """Delete key from appropriate cache backend."""
        backend_name = self._get_backend_for_data_type(data_type)
        backend = self.backends.get(backend_name)

        if not backend:
            return False

        with self._lock:
            deleted = backend.delete(key)
            if deleted:
                self._cache_stats['invalidations'] += 1
                logger.debug(f"Cache key deleted: {key} (backend: {backend_name})")
            return deleted

    def exists(self, key: str, data_type: str = 'default') -> bool:
        """Check if key exists in appropriate cache backend."""
        backend_name = self._get_backend_for_data_type(data_type)
        backend = self.backends.get(backend_name)

        if not backend:
            return False

        return backend.exists(key)

    def invalidate_ticker(self, ticker: str) -> None:
        """Invalidate all cached data for a specific ticker."""
        ticker = ticker.upper()
        patterns = [
            f"stock_info:{ticker}",
            f"financials:{ticker}:",
            f"valuation:{ticker}:",
            f"market_data:{ticker}:"
        ]

        invalidated_count = 0

        for backend in self.backends.values():
            # For exact matches
            for pattern in patterns:
                if pattern.endswith(':'):
                    # Pattern match - we'd need to implement this in backends
                    continue
                else:
                    if backend.delete(pattern):
                        invalidated_count += 1

        self._cache_stats['invalidations'] += invalidated_count
        logger.info(f"Invalidated {invalidated_count} cache entries for {ticker}")

    def invalidate_data_type(self, data_type: str) -> None:
        """Invalidate all cached data of a specific type."""
        backend_name = self._get_backend_for_data_type(data_type)
        backend = self.backends.get(backend_name)

        if backend:
            # This is a simplified implementation
            # In practice, we'd need pattern matching in backends
            logger.info(f"Invalidation requested for data type: {data_type}")

    def clear_all(self) -> None:
        """Clear all caches."""
        for backend in self.backends.values():
            backend.clear()

        logger.info("All caches cleared")

    def cleanup(self) -> None:
        """Clean up expired entries across all backends."""
        for backend_name, backend in self.backends.items():
            if hasattr(backend, 'cleanup_expired'):
                try:
                    cleaned = backend.cleanup_expired()
                    if cleaned > 0:
                        logger.info(f"Cleaned {cleaned} expired entries from {backend_name} cache")
                except Exception as e:
                    logger.warning(f"Error cleaning up {backend_name} cache: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        stats = {
            'manager_stats': self._cache_stats.copy(),
            'backend_stats': {}
        }

        for backend_name, backend in self.backends.items():
            try:
                stats['backend_stats'][backend_name] = backend.get_stats()
            except Exception as e:
                stats['backend_stats'][backend_name] = {'error': str(e)}

        # Calculate overall hit rate
        total_requests = self._cache_stats['hits'] + self._cache_stats['misses']
        if total_requests > 0:
            stats['manager_stats']['hit_rate'] = self._cache_stats['hits'] / total_requests
        else:
            stats['manager_stats']['hit_rate'] = 0.0

        return stats

    def warm_up(self, tickers: List[str]) -> None:
        """Pre-populate cache with commonly accessed data."""
        logger.info(f"Warming up cache for {len(tickers)} tickers")

        # This would typically pre-fetch and cache common data
        # Implementation depends on specific data sources
        for ticker in tickers[:10]:  # Limit for demo
            # Pre-cache basic info
            info_key = CacheKey.stock_info(ticker)
            if not self.exists(info_key, 'stock_info'):
                logger.debug(f"Cache warm-up: {ticker} info not cached")

    def _get_backend_for_data_type(self, data_type: str) -> str:
        """Get appropriate backend name for data type."""
        return self.policy.BACKENDS.get(data_type, 'memory')

    def _get_ttl_for_data_type(self, data_type: str) -> int:
        """Get appropriate TTL for data type."""
        ttl_map = {
            'stock_info': self.policy.STOCK_INFO_TTL,
            'financials': self.policy.FINANCIALS_TTL,
            'valuation': self.policy.VALUATION_TTL,
            'market_data': self.policy.MARKET_DATA_TTL,
            'screening': self.policy.SCREENING_TTL,
            'sp500_tickers': self.policy.SP500_TICKERS_TTL,
        }

        return ttl_map.get(data_type, 3600)  # Default 1 hour


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager(**kwargs) -> CacheManager:
    """Get global cache manager instance (singleton pattern)."""
    global _cache_manager

    if _cache_manager is None:
        _cache_manager = CacheManager(**kwargs)

    return _cache_manager


def reset_cache_manager():
    """Reset global cache manager (useful for testing)."""
    global _cache_manager
    _cache_manager = None
