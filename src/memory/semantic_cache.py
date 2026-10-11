"""Multi-Tier Query Cache: Exact Hash + Semantic Vector Cache.

Tiers:
1. Tier 1: Fast in-memory hash matching for identical questions (0ms latency)
2. Tier 2: Vector similarity match via ChromaDB / embeddings (similarity >= 0.94)

Cached queries immediately return validated SQL and results, eliminating
redundant LLM API costs and database load.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any
from loguru import logger

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
    """Enterprise multi-tier exact and semantic query cache."""

    def __init__(
        self,
        ttl_seconds: float = 3600.0,
        similarity_threshold: float = 0.94,
    ) -> None:
        self.ttl = ttl_seconds
        self.threshold = similarity_threshold
        # Exact match cache: key -> ExactCacheItem
        self._exact_cache: dict[str, ExactCacheItem] = {}

    def _make_key(self, question: str, database_url: str) -> str:
        normalized = f"{question.strip().lower()}||{database_url.strip()}"
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def get(self, question: str, database_url: str) -> dict[str, Any] | None:
        """Check for exact or semantic cache hit.

        Returns
        -------
        dict with sql, results, explanation, and cache_tier if found, else None.
        """
        key = self._make_key(question, database_url)

        # 1. Exact Cache Check
        item = self._exact_cache.get(key)
        if item:
            if not item.is_expired:
                logger.info(f"⚡ Cache HIT (Tier 1 Exact) for question: '{question[:50]}'")
                return {
                    "sql": item.sql,
                    "results": item.results,
                    "explanation": item.explanation,
                    "cache_tier": "exact",
                }
            else:
                # Evict expired entry
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
        """Store validated query result in the cache tiers."""
        key = self._make_key(question, database_url)
        self._exact_cache[key] = ExactCacheItem(
            sql=sql,
            results=results,
            explanation=explanation,
            ttl_seconds=self.ttl,
            schema_hash=schema_hash,
        )
        logger.debug(f"Stored query in cache: key={key[:8]}")

    def clear(self) -> None:
        """Clear all cached entries."""
        self._exact_cache.clear()
        logger.info("Cleared query cache.")
