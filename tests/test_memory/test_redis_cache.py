"""Unit tests for Redis-backed SemanticQueryCache and SlidingWindowRateLimiter."""

import json
import time
from unittest.mock import MagicMock
import pytest

from src.memory.semantic_cache import SemanticQueryCache
from src.api.rate_limiter import SlidingWindowRateLimiter
from src.memory.redis_client import RedisManager


class MockRedis:
    """In-memory mock of Redis client supporting key-value and ZSET commands."""

    def __init__(self):
        self.store = {}
        self.zsets = {}
        self.ttls = {}

    def ping(self):
        return True

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        if ex:
            self.ttls[key] = time.time() + ex
        return True

    def delete(self, *keys):
        count = 0
        for k in keys:
            if k in self.store:
                del self.store[k]
                count += 1
            if k in self.zsets:
                del self.zsets[k]
                count += 1
        return count

    def scan_iter(self, match=None):
        prefix = match.rstrip("*") if match else ""
        for k in list(self.store.keys()):
            if k.startswith(prefix):
                yield k

    def pipeline(self):
        return MockPipeline(self)


class MockPipeline:
    def __init__(self, redis_mock):
        self.redis = redis_mock
        self.commands = []

    def zremrangebyscore(self, key, min_val, max_val):
        self.commands.append(("zremrangebyscore", key, min_val, max_val))
        return self

    def zcard(self, key):
        self.commands.append(("zcard", key))
        return self

    def zadd(self, key, mapping):
        self.commands.append(("zadd", key, mapping))
        return self

    def expire(self, key, seconds):
        self.commands.append(("expire", key, seconds))
        return self

    def execute(self):
        results = []
        for cmd in self.commands:
            op = cmd[0]
            if op == "zremrangebyscore":
                key, min_val, max_val = cmd[1], cmd[2], cmd[3]
                zset = self.redis.zsets.setdefault(key, {})
                cutoff = float(max_val)
                keys_to_remove = [k for k, score in zset.items() if score <= cutoff]
                for k in keys_to_remove:
                    del zset[k]
                results.append(len(keys_to_remove))
            elif op == "zcard":
                key = cmd[1]
                zset = self.redis.zsets.get(key, {})
                results.append(len(zset))
            elif op == "zadd":
                key, mapping = cmd[1], cmd[2]
                zset = self.redis.zsets.setdefault(key, {})
                for k, score in mapping.items():
                    zset[k] = float(score)
                results.append(len(mapping))
            elif op == "expire":
                results.append(True)
        self.commands.clear()
        return results


# ── SemanticQueryCache Tests ──────────────────────────────────────


def test_cache_exact_hit_in_memory_fallback():
    """Verify in-memory caching works when Redis is None."""
    cache = SemanticQueryCache(ttl_seconds=60.0, redis_client=None)

    # Cache miss initially
    assert cache.get("What is our total revenue?", "sqlite:///test.db") is None

    # Set cache
    cache.set(
        question="What is our total revenue?",
        database_url="sqlite:///test.db",
        sql="SELECT SUM(total) FROM orders;",
        results=[{"total": 50000}],
        explanation="Calculates sum of total orders.",
    )

    # Cache hit
    hit = cache.get("What is our total revenue?", "sqlite:///test.db")
    assert hit is not None
    assert hit["sql"] == "SELECT SUM(total) FROM orders;"
    assert hit["results"] == [{"total": 50000}]
    assert hit["cache_tier"] == "exact"


def test_cache_hit_with_redis():
    """Verify Redis exact cache works and takes precedence."""
    mock_redis = MockRedis()
    cache = SemanticQueryCache(ttl_seconds=300.0, redis_client=mock_redis)

    cache.set(
        question="Show active users",
        database_url="sqlite:///test.db",
        sql="SELECT * FROM users WHERE active = 1;",
        results=[{"id": 1, "name": "Alice"}],
        explanation="Active users query",
    )

    # Should be in mock redis store
    assert len(mock_redis.store) == 1

    hit = cache.get("Show active users", "sqlite:///test.db")
    assert hit is not None
    assert hit["sql"] == "SELECT * FROM users WHERE active = 1;"
    assert hit["cache_tier"] == "redis_exact"


def test_cache_clear_redis_and_memory():
    """Verify clear empties both Redis and in-memory caches."""
    mock_redis = MockRedis()
    cache = SemanticQueryCache(ttl_seconds=300.0, redis_client=mock_redis)

    cache.set(
        question="Q1",
        database_url="sqlite:///test.db",
        sql="SELECT 1;",
        results=[{"1": 1}],
        explanation="test",
    )
    assert len(mock_redis.store) == 1
    assert len(cache._exact_cache) == 1

    cache.clear()
    assert len(mock_redis.store) == 0
    assert len(cache._exact_cache) == 0


def test_cache_graceful_fallback_on_redis_error():
    """Verify cache silently falls back to in-memory if Redis raises errors."""
    broken_redis = MagicMock()
    broken_redis.get.side_effect = Exception("Redis connection refused")
    broken_redis.set.side_effect = Exception("Redis write failed")

    cache = SemanticQueryCache(ttl_seconds=60.0, redis_client=broken_redis)

    # Setting should not throw
    cache.set(
        question="Safe query",
        database_url="sqlite:///test.db",
        sql="SELECT 42;",
        results=[{"val": 42}],
        explanation="Safe",
    )

    # Getting should still return from in-memory fallback
    hit = cache.get("Safe query", "sqlite:///test.db")
    assert hit is not None
    assert hit["sql"] == "SELECT 42;"
    assert hit["cache_tier"] == "exact"


# ── Rate Limiter Tests ────────────────────────────────────────────


def test_rate_limiter_in_memory_allowed_and_blocked():
    """Verify in-memory sliding window rate limits."""
    limiter = SlidingWindowRateLimiter(max_requests_per_minute=3, redis_client=None)

    allowed, rem = limiter.is_allowed("client-1")
    assert allowed is True
    assert rem == 2

    allowed, rem = limiter.is_allowed("client-1")
    assert allowed is True
    assert rem == 1

    allowed, rem = limiter.is_allowed("client-1")
    assert allowed is True
    assert rem == 0

    # 4th request blocked
    allowed, rem = limiter.is_allowed("client-1")
    assert allowed is False
    assert rem == 0

    # Different client is not blocked
    allowed_other, _ = limiter.is_allowed("client-2")
    assert allowed_other is True


def test_rate_limiter_redis_allowed_and_blocked():
    """Verify Redis sliding window rate limits using ZSET."""
    mock_redis = MockRedis()
    limiter = SlidingWindowRateLimiter(max_requests_per_minute=2, redis_client=mock_redis)

    allowed, rem = limiter.is_allowed("client-ip-123")
    assert allowed is True
    assert rem == 1

    allowed, rem = limiter.is_allowed("client-ip-123")
    assert allowed is True
    assert rem == 0

    # 3rd request blocked
    allowed, rem = limiter.is_allowed("client-ip-123")
    assert allowed is False
    assert rem == 0


def test_rate_limiter_fallback_on_redis_error():
    """Verify rate limiter falls back to in-memory on Redis error."""
    broken_redis = MagicMock()
    broken_redis.pipeline.side_effect = Exception("Redis cluster unavailable")

    limiter = SlidingWindowRateLimiter(max_requests_per_minute=2, redis_client=broken_redis)

    # Should fall back to in-memory without raising
    allowed, rem = limiter.is_allowed("client-ip-fallback")
    assert allowed is True
    assert rem == 1


# ── RedisManager Tests ────────────────────────────────────────────


def test_redis_manager_disabled_returns_none():
    """Verify RedisManager returns None when disabled."""
    mgr = RedisManager()
    with pytest.MonkeyPatch.context() as mp:
        from src.config.settings import settings
        mp.setattr(settings, "redis_enabled", False)
        assert mgr.get_client() is None
        assert mgr.is_available() is False
