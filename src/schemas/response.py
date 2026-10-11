"""Pydantic response models for the FastAPI endpoints."""

from typing import Any
from pydantic import BaseModel, Field


class QueryResponse(BaseModel):
    """Full response from the SQLWhisperer pipeline."""

    query_id: int | None = Field(default=None, description="Unique ID for this query")
    question: str = Field(description="Original natural language question")
    sql: str = Field(description="Generated (or corrected) SQL query")
    results: list[dict[str, Any]] = Field(
        default_factory=list, description="Query result rows"
    )
    row_count: int = Field(default=0, description="Total number of result rows")
    execution_time_ms: float = Field(
        default=0.0, description="SQL execution time in milliseconds"
    )
    explanation: str = Field(
        default="", description="Plain-English explanation of the results"
    )
    confidence: float = Field(
        default=0.0,
        description="Confidence score (0.0–1.0) that results answer the question",
    )
    refinement_count: int = Field(
        default=0, description="Number of refinement retries used"
    )
    success: bool = Field(description="Whether the pipeline succeeded")
    error: str | None = Field(
        default=None, description="Error message if the pipeline failed"
    )


class FeedbackResponse(BaseModel):
    """Response after submitting feedback."""

    status: str = Field(description="'ok' or 'error'")
    message: str = Field(description="Human-readable result message")


class HistoryItem(BaseModel):
    """Single item in the query history list."""

    id: int
    question: str
    sql: str
    was_successful: bool
    confidence: float
    created_at: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "0.1.0"
    dialect: str = "SQLite"
    llm_provider: str = "openai"


class ColumnInfo(BaseModel):
    """Column metadata for Schema Explorer."""

    name: str
    type: str
    primary_key: bool = False
    nullable: bool = True


class TableSchemaInfo(BaseModel):
    """Table schema details for Schema Explorer."""

    name: str
    columns: list[ColumnInfo] = []
    row_count: int = 0
    sample_rows: list[dict[str, Any]] = []


class DatabaseTestResponse(BaseModel):
    """Response from database connection test."""

    success: bool
    dialect: str = "Unknown"
    tables: list[str] = []
    table_count: int = 0
    error: str | None = None
