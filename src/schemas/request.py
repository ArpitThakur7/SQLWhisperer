from typing import Any
from pydantic import BaseModel, Field, model_validator


class QueryRequest(BaseModel):
    """Natural language query input with optional per-query connection override."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="Natural language question to convert to SQL",
    )
    database_url: str | None = Field(
        default=None,
        description="Optional custom database connection URL override (e.g. postgresql://..., sqlite:///...)",
    )
    api_key: str | None = Field(
        default=None,
        description="Optional API key override for this session",
    )
    llm_provider: str | None = Field(
        default=None,
        description="Optional LLM provider override ('openai', 'groq', 'gemini', 'ollama', 'openrouter')",
    )
    model: str | None = Field(
        default=None,
        description="Optional model override",
    )
    ollama_base_url: str | None = Field(
        default=None,
        description="Optional Ollama/Local SLM base URL override (e.g. http://localhost:8001)",
    )


class DatabaseConnectRequest(BaseModel):
    """Test database connection and retrieve schema."""

    database_url: str = Field(
        ...,
        description="Database connection URL to validate (e.g. postgresql://..., sqlite:///...)",
    )


class FeedbackRequest(BaseModel):
    """User feedback on a query result."""

    query_id: int = Field(
        ..., description="ID of the query to provide feedback for"
    )
    feedback: str = Field(
        default="positive",
        pattern=r"^(positive|negative|corrected)$",
        description="Feedback type: 'positive', 'negative', or 'corrected'",
    )
    rating: str | None = Field(
        default=None,
        description="Alternative shorthand rating: 'up', 'down'",
    )
    corrected_sql: str | None = Field(
        default=None,
        description="Corrected SQL — required when feedback is 'corrected'",
    )

    @model_validator(mode="before")
    @classmethod
    def normalize_feedback_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            raw_rating = data.get("rating")
            raw_fb = data.get("feedback")
            # Map shorthand 'up'/'down' to 'positive'/'negative'
            mapping = {"up": "positive", "down": "negative"}
            if raw_rating and not raw_fb:
                data["feedback"] = mapping.get(str(raw_rating).lower().strip(), str(raw_rating))
            elif raw_fb and str(raw_fb).lower().strip() in mapping:
                data["feedback"] = mapping[str(raw_fb).lower().strip()]
        return data

