"""Centralized configuration via Pydantic Settings.

All values are read from environment variables or a .env file.
"""

from typing import Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM Provider Config ───────────────────────────────────────
    llm_provider: str = "openai"  # "openai", "groq", "gemini", "ollama", "openrouter", "demo"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_temperature: float = 0.0

    # Free Cloud Providers
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    openrouter_api_key: str = ""
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"

    # Local Ollama config (100% Free & Offline)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:7b"

    # ── Target Database ───────────────────────────────────────────
    # Defaults to zero-setup SQLite demo DB, or PostgreSQL if specified
    database_url: str = "sqlite:///./data/demo_ecommerce.db"

    # ── Query History (SQLite) ────────────────────────────────────
    history_db_url: str = "sqlite:///./data/query_history.db"

    # ── ChromaDB (Few-Shot Store) ─────────────────────────────────
    chroma_persist_dir: str = "./data/chroma"
    chroma_collection_name: str = "few_shot_examples"

    # ── Chain Config ──────────────────────────────────────────────
    max_refinement_retries: int = 3
    max_result_rows: int = 100
    query_timeout_seconds: int = 30

    # ── Security ──────────────────────────────────────────────────
    allowed_sql_commands: str | list[str] = ["SELECT"]
    blocked_tables: str | list[str] = []

    @field_validator("allowed_sql_commands", "blocked_tables", mode="after")
    @classmethod
    def ensure_list(cls, value: Any) -> list[str]:
        """Convert string (comma-separated or single) into list of strings."""
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            if value.startswith("[") and value.endswith("]"):
                import json
                try:
                    res = json.loads(value)
                    if isinstance(res, list):
                        return [str(x).strip() for x in res]
                except Exception:
                    pass
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(x).strip() for x in value]
        return []


settings = Settings()
