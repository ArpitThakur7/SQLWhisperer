"""Production In-Memory Sliding Window Rate Limiter.

Prevents API key exhaustion, DoS attacks, and runaway automated loops
by tracking requests per client IP / API key within a 60-second window.
"""

from __future__ import annotations

import time
from collections import defaultdict
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from loguru import logger


class SlidingWindowRateLimiter:
    """Sliding window in-memory rate limiter."""

    def __init__(self, max_requests_per_minute: int = 60) -> None:
        self.max_requests = max_requests_per_minute
        self.window_seconds = 60.0
        # Map: client_identifier -> list of timestamps
        self._history: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, identifier: str) -> tuple[bool, int]:
        """Check if request is within limits.

        Returns
        -------
        (allowed, remaining_requests)
        """
        now = time.time()
        cutoff = now - self.window_seconds

        # Clean timestamps older than 60 seconds
        timestamps = [t for t in self._history[identifier] if t > cutoff]
        self._history[identifier] = timestamps

        if len(timestamps) >= self.max_requests:
            return False, 0

        # Record this request
        self._history[identifier].append(now)
        remaining = self.max_requests - len(self._history[identifier])
        return True, remaining


class RateLimitMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware that enforces sliding-window rate limits."""

    def __init__(self, app, max_requests_per_minute: int = 120):
        super().__init__(app)
        self.limiter = SlidingWindowRateLimiter(max_requests_per_minute)

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
