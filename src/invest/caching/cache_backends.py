"""
Cache Backend Implementations

This module provides different caching backend implementations:
- MemoryCache: In-memory LRU cache for fast access
- FileCache: Persistent file-based cache
- RedisCache: Redis-based distributed cache (optional)

Each backend implements a common interface for consistency.
"""

import hashlib
import logging
import pickle
import time
from abc import ABC, abstractmethod
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache by key."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache with optional TTL in seconds."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete key from cache. Returns True if key existed."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all cached items."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        pass


class MemoryCache(CacheBackend):
    """In-memory LRU cache with TTL support."""

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        """
        Initialize memory cache.

        Parameters
        ----------
        max_size : int
            Maximum number of items to store
        default_ttl : int
            Default TTL in seconds
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_times: Dict[str, float] = {}
        self._lock = Lock()

        # Statistics
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._evictions = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value from memory cache."""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            entry = self._cache[key]

            # Check expiration
            if self._is_expired(entry):
                del self._cache[key]
                del self._access_times[key]
                self._misses += 1
                return None

            # Update access time for LRU
            self._access_times[key] = time.time()
            self._hits += 1

            return entry['value']

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in memory cache."""
        with self._lock:
            ttl = ttl or self.default_ttl
            expires_at = time.time() + ttl

            # Check if we need to evict items
            if len(self._cache) >= self.max_size and key not in self._cache:
                self._evict_lru()

            self._cache[key] = {
                'value': value,
                'expires_at': expires_at,
                'created_at': time.time()
            }
            self._access_times[key] = time.time()
            self._sets += 1

    def delete(self, key: str) -> bool:
        """Delete key from memory cache."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                del self._access_times[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all cached items."""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
            logger.info("Memory cache cleared")

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        with self._lock:
            if key not in self._cache:
                return False

            entry = self._cache[key]
            if self._is_expired(entry):
                del self._cache[key]
                del self._access_times[key]
                return False

            return True

    def get_stats(self) -> Dict[str, Any]:
        """Get memory cache statistics."""
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests) if total_requests > 0 else 0

            return {
                'backend': 'memory',
                'size': len(self._cache),
                'max_size': self.max_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate,
                'sets': self._sets,
                'evictions': self._evictions,
            }

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """Check if cache entry is expired."""
        return time.time() > entry['expires_at']

    def _evict_lru(self) -> None:
        """Evict least recently used item."""
        if not self._access_times:
            return

        # Find least recently used key
        lru_key = min(self._access_times.keys(), key=self._access_times.get)
        del self._cache[lru_key]
        del self._access_times[lru_key]
        self._evictions += 1


class FileCache(CacheBackend):
    """Persistent file-based cache."""

    def __init__(self, cache_dir: str = ".cache", default_ttl: int = 86400):
        """
        Initialize file cache.

        Parameters
        ----------
        cache_dir : str
            Directory to store cache files
        default_ttl : int
            Default TTL in seconds (24 hours)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl
        self._lock = Lock()

        # Statistics
        self._hits = 0
        self._misses = 0
        self._sets = 0

    def get(self, key: str) -> Optional[Any]:
        """Get value from file cache."""
        cache_file = self._get_cache_file(key)

        with self._lock:
            try:
                if not cache_file.exists():
                    self._misses += 1
                    return None

                with open(cache_file, 'rb') as f:
                    cached_data = pickle.load(f)

                # Check expiration
                if time.time() > cached_data['expires_at']:
                    cache_file.unlink()  # Delete expired file
                    self._misses += 1
                    return None

                self._hits += 1
                return cached_data['value']

            except Exception as e:
                logger.warning(f"Error reading cache file {cache_file}: {e}")
                # Clean up corrupted file
                if cache_file.exists():
                    cache_file.unlink()
                self._misses += 1
                return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in file cache."""
        cache_file = self._get_cache_file(key)
        ttl = ttl or self.default_ttl

        cached_data = {
            'value': value,
            'expires_at': time.time() + ttl,
            'created_at': time.time(),
            'key': key
        }

        with self._lock:
            try:
                with open(cache_file, 'wb') as f:
                    pickle.dump(cached_data, f)
                self._sets += 1

            except Exception as e:
                logger.error(f"Error writing cache file {cache_file}: {e}")

    def delete(self, key: str) -> bool:
        """Delete key from file cache."""
        cache_file = self._get_cache_file(key)

        with self._lock:
            if cache_file.exists():
                cache_file.unlink()
                return True
            return False

    def clear(self) -> None:
        """Clear all cached files."""
        with self._lock:
            try:
                for cache_file in self.cache_dir.glob("*.cache"):
                    cache_file.unlink()
                logger.info("File cache cleared")
            except Exception as e:
                logger.error(f"Error clearing file cache: {e}")

    def exists(self, key: str) -> bool:
        """Check if key exists and is not expired."""
        cache_file = self._get_cache_file(key)

        if not cache_file.exists():
            return False

        try:
            with open(cache_file, 'rb') as f:
                cached_data = pickle.load(f)

            # Check expiration
            if time.time() > cached_data['expires_at']:
                cache_file.unlink()
                return False

            return True

        except Exception:
            # Clean up corrupted file
            if cache_file.exists():
                cache_file.unlink()
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get file cache statistics."""
        with self._lock:
            # Count cache files
            cache_files = list(self.cache_dir.glob("*.cache"))
            total_size = sum(f.stat().st_size for f in cache_files if f.exists())

            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests) if total_requests > 0 else 0

            return {
                'backend': 'file',
                'cache_dir': str(self.cache_dir),
                'size': len(cache_files),
                'total_size_bytes': total_size,
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate,
                'sets': self._sets,
            }

    def _get_cache_file(self, key: str) -> Path:
        """Get cache file path for key."""
        # Create a safe filename from the key
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.cache"

    def cleanup_expired(self) -> int:
        """Clean up expired cache files. Returns number of files deleted."""
        deleted_count = 0

        with self._lock:
            for cache_file in self.cache_dir.glob("*.cache"):
                try:
                    with open(cache_file, 'rb') as f:
                        cached_data = pickle.load(f)

                    if time.time() > cached_data['expires_at']:
                        cache_file.unlink()
                        deleted_count += 1

                except Exception:
                    # Delete corrupted files too
                    cache_file.unlink()
                    deleted_count += 1

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired cache files")

        return deleted_count


class RedisCache(CacheBackend):
    """Redis-based distributed cache (optional - requires redis-py)."""

    def __init__(self, host: str = 'localhost', port: int = 6379,
                 db: int = 0, password: Optional[str] = None,
                 default_ttl: int = 3600, key_prefix: str = 'invest:'):
        """
        Initialize Redis cache.

        Parameters
        ----------
        host : str
            Redis server host
        port : int
            Redis server port
        db : int
            Redis database number
        password : Optional[str]
            Redis password if required
        default_ttl : int
            Default TTL in seconds
        key_prefix : str
            Prefix for all cache keys
        """
        self.default_ttl = default_ttl
        self.key_prefix = key_prefix

        try:
            import redis
            self.redis = redis.Redis(
                host=host, port=port, db=db, password=password,
                decode_responses=False  # We handle binary data
            )
            # Test connection
            self.redis.ping()
            logger.info(f"Connected to Redis at {host}:{port}")

        except ImportError:
            raise ImportError("redis-py package is required for RedisCache")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}")

    def get(self, key: str) -> Optional[Any]:
        """Get value from Redis cache."""
        try:
            redis_key = self.key_prefix + key
            cached_data = self.redis.get(redis_key)

            if cached_data is None:
                return None

            return pickle.loads(cached_data)

        except Exception as e:
            logger.warning(f"Error getting Redis cache key {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in Redis cache."""
        try:
            redis_key = self.key_prefix + key
            ttl = ttl or self.default_ttl

            cached_data = pickle.dumps(value)
            self.redis.setex(redis_key, ttl, cached_data)

        except Exception as e:
            logger.error(f"Error setting Redis cache key {key}: {e}")

    def delete(self, key: str) -> bool:
        """Delete key from Redis cache."""
        try:
            redis_key = self.key_prefix + key
            result = self.redis.delete(redis_key)
            return result > 0

        except Exception as e:
            logger.error(f"Error deleting Redis cache key {key}: {e}")
            return False

    def clear(self) -> None:
        """Clear all cached items with our prefix."""
        try:
            pattern = self.key_prefix + "*"
            keys = self.redis.keys(pattern)
            if keys:
                self.redis.delete(*keys)
            logger.info("Redis cache cleared")

        except Exception as e:
            logger.error(f"Error clearing Redis cache: {e}")

    def exists(self, key: str) -> bool:
        """Check if key exists in Redis cache."""
        try:
            redis_key = self.key_prefix + key
            return self.redis.exists(redis_key) > 0

        except Exception as e:
            logger.warning(f"Error checking Redis cache key {key}: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get Redis cache statistics."""
        try:
            info = self.redis.info('memory')
            pattern = self.key_prefix + "*"
            keys = self.redis.keys(pattern)

            return {
                'backend': 'redis',
                'size': len(keys),
                'memory_used_bytes': info.get('used_memory', 0),
                'connected_clients': self.redis.info('clients').get('connected_clients', 0),
            }

        except Exception as e:
            logger.error(f"Error getting Redis stats: {e}")
            return {'backend': 'redis', 'error': str(e)}
