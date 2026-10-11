"""SQLAlchemy ORM models for the query history database (SQLite)."""

from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Text,
    JSON,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class QueryRecord(Base):
    """Stores every query attempt for learning, analytics, and audit.

    Each row represents a single end-to-end pipeline invocation,
    regardless of whether it succeeded or failed.
    """

    __tablename__ = "query_records"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Input ─────────────────────────────────────────────────────
    question = Column(Text, nullable=False)

    # ── Generated artefacts ───────────────────────────────────────
    generated_sql = Column(Text, nullable=False)
    final_sql = Column(Text, nullable=False)

    # ── Execution results ─────────────────────────────────────────
    results_preview = Column(Text)  # First 5 rows as JSON string
    row_count = Column(Integer, default=0)
    execution_time_ms = Column(Float, default=0.0)

    # ── Quality signals ───────────────────────────────────────────
    was_successful = Column(Boolean, default=False)
    confidence = Column(Float, default=0.0)
    refinement_count = Column(Integer, default=0)
    error_message = Column(Text)

    # ── Explanation ───────────────────────────────────────────────
    explanation = Column(Text)

    # ── User feedback ─────────────────────────────────────────────
    user_feedback = Column(String(20))  # 'positive', 'negative', 'corrected'
    corrected_sql = Column(Text)  # User-provided correction

    # ── Metadata ──────────────────────────────────────────────────
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    metadata_ = Column("metadata", JSON)

    def __repr__(self) -> str:
        return (
            f"<QueryRecord(id={self.id}, "
            f"success={self.was_successful}, "
            f"confidence={self.confidence})>"
        )
