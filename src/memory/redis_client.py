"""Enterprise Redis Client Connection Manager.

Provides a thread-safe Redis client with connection pooling, fast health
checks, and automatic, zero-overhead fallback to local in-memory storage
when Redis is unavailable or unconfigured.
"""

from __future__ import annotations

import threading
import time
from typing import Any
from loguru import logger

from src.config.settings import settings

try:
    import redis
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    redis = None  # type: ignore


class RedisManager:
    """Thread-safe Redis client manager with connectivity health checking and cooldown."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client: Any | None = None
        self._is_available: bool | None = None
        self._last_check_time: float = 0.0
        self._check_cooldown_seconds: float = 30.0  # Avoid connection attempts on every request when offline
        self._logged_warning: bool = False

    def get_client(self) -> Any | None:
        """Return an active Redis client if reachable, or None if unavailable."""
        if not HAS_REDIS or not settings.redis_enabled or not settings.redis_url:
            return None

        now = time.time()

        # If previously checked and unavailable, respect cooldown before retrying
        with self._lock:
            if self._is_available is False and (now - self._last_check_time < self._check_cooldown_seconds):
                return None

            if self._is_available is True and self._client is not None:
                return self._client

        # Attempt to establish / verify connection
        with self._lock:
            # Double-check inside lock
            if self._is_available is True and self._client is not None:
                return self._client
            if self._is_available is False and (now - self._last_check_time < self._check_cooldown_seconds):
                return None

            self._last_check_time = now

            try:
                client = redis.Redis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=0.3,
                    socket_timeout=0.5,
                    decode_responses=True,
                )
                # Quick health ping
                client.ping()
                self._client = client
                self._is_available = True
                logger.info(f"⚡ Redis cache & rate-limiter connected at {settings.redis_url}")
                return self._client
            except Exception as exc:
                self._client = None
                self._is_available = False
                if not self._logged_warning:
                    logger.info(
                        f"ℹ️ Redis not reachable at '{settings.redis_url}' ({exc}). "
                        "Using in-memory caching and rate-limiting (zero-setup mode)."
                    )
                    self._logged_warning = True
                return None

    def is_available(self) -> bool:
        """Check whether Redis is connected and available."""
        return self.get_client() is not None

    def reset(self) -> None:
        """Reset connection state (useful for tests and dynamic configuration)."""
        with self._lock:
            if self._client is not None:
                try:
                    self._client.close()
                except Exception:
                    pass
            self._client = None
            self._is_available = None
            self._last_check_time = 0.0
            self._logged_warning = False


# Global singleton instance
redis_manager = RedisManager()


def get_redis_client() -> Any | None:
    """Convenience getter for the Redis client."""
    return redis_manager.get_client()


def is_redis_available() -> bool:
    """Convenience checker for Redis availability."""
    return redis_manager.is_available()
