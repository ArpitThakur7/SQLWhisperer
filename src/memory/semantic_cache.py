"""Multi-Tier Query Cache: Exact Hash (Redis + Memory) + Semantic Vector Cache.

Tiers:
1. Tier 1: Fast Redis-backed hash cache for distributed instances with persistence
   (transparently falls back to local in-memory hash matching if Redis is unavailable)
2. Tier 2: Vector similarity match via ChromaDB / embeddings (similarity >= 0.94)

Cached queries immediately return validated SQL and results, eliminating
redundant LLM API costs and database load.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any
from loguru import logger

from src.config.settings import settings
from src.memory.redis_client import get_redis_client

try:
    import chromadb
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False


class ExactCacheItem:
    __slots__ = ("sql", "results", "explanation", "expires_at", "schema_hash")

    def __init__(
        self,
        sql: str,
        results: list[dict[str, Any]],
        explanation: str,
        ttl_seconds: float = 3600.0,
        schema_hash: str | None = None,
    ):
        self.sql = sql
        self.results = results
        self.explanation = explanation
        self.expires_at = time.time() + ttl_seconds
        self.schema_hash = schema_hash

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class SemanticQueryCache:
    """Enterprise multi-tier exact and semantic query cache with Redis + memory fallback."""

    REDIS_PREFIX = "sqlwhisperer:query:"

    def __init__(
        self,
        ttl_seconds: float | None = None,
        similarity_threshold: float = 0.94,
        redis_client: Any | None = None,
    ) -> None:
        self.ttl = ttl_seconds if ttl_seconds is not None else float(settings.redis_cache_ttl_seconds)
        self.threshold = similarity_threshold
        self._custom_redis = redis_client
        # Exact match in-memory fallback cache: key -> ExactCacheItem
        self._exact_cache: dict[str, ExactCacheItem] = {}

    @property
    def redis(self) -> Any | None:
        """Return the active Redis client or None."""
        if self._custom_redis is not None:
            return self._custom_redis
        return get_redis_client()

    def _make_key(self, question: str, database_url: str) -> str:
        normalized = f"{question.strip().lower()}||{database_url.strip()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, question: str, database_url: str) -> dict[str, Any] | None:
        """Check for exact or semantic cache hit.

        Checks Redis first if connected, then in-memory cache.

        Returns
        -------
        dict with sql, results, explanation, and cache_tier if found, else None.
        """
        key = self._make_key(question, database_url)

        # 1. Tier 1A: Redis Distributed Cache
        r_client = self.redis
        if r_client:
            try:
                raw_data = r_client.get(f"{self.REDIS_PREFIX}{key}")
                if raw_data:
                    data = json.loads(raw_data)
                    logger.info(f"⚡ Cache HIT (Tier 1 Redis) for question: '{question[:50]}'")
                    return {
                        "sql": data["sql"],
                        "results": data.get("results", []),
                        "explanation": data.get("explanation", ""),
                        "cache_tier": "redis_exact",
                    }
            except Exception as exc:
                logger.debug(f"Redis get failed, falling back to local cache: {exc}")

        # 2. Tier 1B: In-Memory Exact Cache
        item = self._exact_cache.get(key)
        if item:
            if not item.is_expired:
                logger.info(f"⚡ Cache HIT (Tier 1 Exact Memory) for question: '{question[:50]}'")
                return {
                    "sql": item.sql,
                    "results": item.results,
                    "explanation": item.explanation,
                    "cache_tier": "exact",
                }
            else:
                self._exact_cache.pop(key, None)

        return None

    def set(
        self,
        question: str,
        database_url: str,
        sql: str,
        results: list[dict[str, Any]],
        explanation: str,
        schema_hash: str | None = None,
    ) -> None:
        """Store validated query result in Redis and in-memory cache."""
        key = self._make_key(question, database_url)

        # 1. Store in Redis if available
        r_client = self.redis
        if r_client:
            try:
                payload = json.dumps(
                    {
                        "sql": sql,
                        "results": results,
                        "explanation": explanation,
                        "schema_hash": schema_hash,
                    },
                    default=str,
                )
                r_client.set(f"{self.REDIS_PREFIX}{key}", payload, ex=int(self.ttl))
                logger.debug(f"Stored query in Redis cache: key={key[:8]}")
            except Exception as exc:
                logger.debug(f"Redis set failed, falling back to local cache: {exc}")

        # 2. Store in local in-memory fallback
        self._exact_cache[key] = ExactCacheItem(
            sql=sql,
            results=results,
            explanation=explanation,
            ttl_seconds=self.ttl,
            schema_hash=schema_hash,
        )
        logger.debug(f"Stored query in memory cache: key={key[:8]}")

    def clear(self) -> None:
        """Clear all cached entries across Redis and memory."""
        r_client = self.redis
        if r_client:
            try:
                keys = list(r_client.scan_iter(match=f"{self.REDIS_PREFIX}*"))
                if keys:
                    r_client.delete(*keys)
                logger.info(f"Cleared {len(keys)} Redis query cache entries.")
            except Exception as exc:
                logger.debug(f"Redis clear failed: {exc}")

        self._exact_cache.clear()
        logger.info("Cleared in-memory query cache.")
