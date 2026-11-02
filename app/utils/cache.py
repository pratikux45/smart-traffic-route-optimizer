"""
In-memory caching utility with TTL support.
"""

import time
import threading
from typing import Any, Dict, Optional, Tuple
from app.config import settings


class SimpleTTLCache:
    """Thread-safe in-memory key-value cache with Time-To-Live (TTL)."""

    def __init__(self, default_ttl_seconds: int = 300, max_size: int = 500):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._default_ttl = default_ttl_seconds
        self._max_size = max_size
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from the cache if it hasn't expired."""
        with self._lock:
            if key not in self._cache:
                return None

            val, expiry = self._cache[key]
            if time.time() > expiry:
                del self._cache[key]
                return None

            return val

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value in the cache with specified or default TTL."""
        with self._lock:
            # Evict expired items if size limit reached
            if len(self._cache) >= self._max_size:
                now = time.time()
                expired_keys = [k for k, (_, exp) in self._cache.items() if now > exp]
                for k in expired_keys:
                    del self._cache[k]

                # If still full, drop the oldest entry
                if len(self._cache) >= self._max_size:
                    first_key = next(iter(self._cache))
                    del self._cache[first_key]

            ttl_val = ttl if ttl is not None else self._default_ttl
            expiry = time.time() + ttl_val
            self._cache[key] = (value, expiry)

    def clear(self) -> None:
        """Clear all entries in the cache."""
        with self._lock:
            self._cache.clear()


# Global cache instances configured with TTL from settings
geocode_cache = SimpleTTLCache(default_ttl_seconds=settings.GEOCODE_CACHE_TTL)
router_cache = SimpleTTLCache(default_ttl_seconds=settings.ROUTE_CACHE_TTL)
overpass_cache = SimpleTTLCache(default_ttl_seconds=settings.SIGNAL_CACHE_TTL)
