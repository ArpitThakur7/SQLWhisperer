"""Production Sliding Window Rate Limiter with Distributed Redis & In-Memory Fallback.

Prevents API key exhaustion, DoS attacks, and runaway automated loops
by tracking requests per client IP / API key within a 60-second window.
When Redis is connected, rate limits are enforced consistently across multiple
API instances/workers using Redis Sorted Sets (ZSET). When Redis is unavailable,
it transparently falls back to a local in-memory sliding window.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger

from src.memory.redis_client import get_redis_client


class SlidingWindowRateLimiter:
    """Sliding window rate limiter with Redis Sorted Set backend and memory fallback."""

    REDIS_KEY_PREFIX = "sqlwhisperer:ratelimit:"

    def __init__(
        self,
        max_requests_per_minute: int = 60,
        redis_client: Any | None = None,
    ) -> None:
        self.max_requests = max_requests_per_minute
        self.window_seconds = 60.0
        self._custom_redis = redis_client
        # In-memory fallback: client_identifier -> list of timestamps
        self._history: dict[str, list[float]] = defaultdict(list)

    @property
    def redis(self) -> Any | None:
        if self._custom_redis is not None:
            return self._custom_redis
        return get_redis_client()

    def _is_allowed_in_memory(self, identifier: str) -> tuple[bool, int]:
        """In-memory fallback sliding window calculation."""
        now = time.time()
        cutoff = now - self.window_seconds

        timestamps = [t for t in self._history[identifier] if t > cutoff]
        self._history[identifier] = timestamps

        if len(timestamps) >= self.max_requests:
            return False, 0

        self._history[identifier].append(now)
        remaining = self.max_requests - len(self._history[identifier])
        return True, max(0, remaining)

    def is_allowed(self, identifier: str) -> tuple[bool, int]:
        """Check if request is within rate limits.

        Uses Redis ZSET if available, else falls back to in-memory sliding window.

        Returns
        -------
        (allowed, remaining_requests)
        """
        r_client = self.redis
        if r_client:
            try:
                now = time.time()
                cutoff = now - self.window_seconds
                redis_key = f"{self.REDIS_KEY_PREFIX}{identifier}"

                pipe = r_client.pipeline()
                pipe.zremrangebyscore(redis_key, "-inf", cutoff)
                pipe.zcard(redis_key)
                res = pipe.execute()

                current_count = res[1]
                if current_count >= self.max_requests:
                    return False, 0

                member = f"{now}:{time.perf_counter_ns()}"
                pipe = r_client.pipeline()
                pipe.zadd(redis_key, {member: now})
                pipe.expire(redis_key, int(self.window_seconds * 2))
                pipe.execute()

                remaining = max(0, self.max_requests - (current_count + 1))
                return True, remaining
            except Exception as exc:
                logger.debug(f"Redis rate-limit check failed ({exc}), using memory fallback.")

        return self._is_allowed_in_memory(identifier)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware that enforces sliding-window rate limits."""

    def __init__(self, app, max_requests_per_minute: int = 120, redis_client: Any | None = None):
        super().__init__(app)
        self.limiter = SlidingWindowRateLimiter(
            max_requests_per_minute=max_requests_per_minute,
            redis_client=redis_client,
        )

    async def dispatch(self, request: Request, call_next):
        # Exclude static/health/docs checks from rate limits
        path = request.url.path
        if path.startswith(("/docs", "/redoc", "/openapi.json", "/api/v1/health")):
            return await call_next(request)

        # Identifier: authorization header or client IP
        auth_header = request.headers.get("X-API-Key") or request.headers.get("Authorization", "")
        client_ip = request.client.host if request.client else "unknown_client"
        identifier = f"{client_ip}:{auth_header[:16]}" if auth_header else client_ip

        allowed, remaining = self.limiter.is_allowed(identifier)
        if not allowed:
            logger.warning(f"Rate limit exceeded for client: {identifier}")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Too many requests. Please slow down.",
                    "retry_after_seconds": 60,
                },
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
