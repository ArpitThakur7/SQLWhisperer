"""Per-request session configuration.

Instead of mutating the global ``settings`` singleton (which causes race
conditions when multiple users hit the API concurrently), each request
builds a lightweight ``SessionConfig`` that overrides only the fields the
caller specified.  This config is propagated through the pipeline so
every component sees the correct database, LLM provider, and API key
for *that specific request*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from src.config.settings import settings


@dataclass(frozen=True, slots=True)
class SessionConfig:
    """Immutable per-request configuration overrides.

    Any field left as ``None`` falls back to the global ``settings`` value.
    """

    database_url: str | None = None
    llm_provider: str | None = None
    api_key: str | None = None
    model: str | None = None
    ollama_base_url: str | None = None

    # ── Resolved accessors (with fallback to global settings) ────

    @property
    def resolved_ollama_base_url(self) -> str:
        return (self.ollama_base_url or settings.ollama_base_url).strip()

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or settings.database_url

    @property
    def resolved_llm_provider(self) -> str:
        return (self.llm_provider or settings.llm_provider).lower().strip()

    @property
    def resolved_model(self) -> str:
        """Return the model name for the active provider."""
        if self.model:
            return self.model.strip()
        provider = self.resolved_llm_provider
        return {
            "groq": settings.groq_model,
            "gemini": settings.gemini_model,
            "openrouter": settings.openrouter_model,
            "ollama": settings.ollama_model,
        }.get(provider, settings.openai_model)

    @property
    def resolved_api_key(self) -> str:
        """Return the API key for the active provider."""
        if self.api_key:
            return self.api_key.strip()
        provider = self.resolved_llm_provider
        return {
            "groq": settings.groq_api_key,
            "gemini": settings.gemini_api_key,
            "openrouter": settings.openrouter_api_key,
            "ollama": "ollama",
        }.get(provider, settings.openai_api_key)

    @property
    def resolved_temperature(self) -> float:
        return settings.openai_temperature


# Convenience default — uses all global settings, no overrides.
DEFAULT_SESSION = SessionConfig()
