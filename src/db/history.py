"""Query history manager.

Persists every pipeline invocation to SQLite for analytics,
feedback tracking, and potential few-shot seeding.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from src.db.models import Base, QueryRecord
from src.config.settings import settings
from loguru import logger


class QueryHistory:
    """CRUD interface for the query history SQLite database."""

    def __init__(self, db_url: str | None = None) -> None:
        url = db_url or settings.history_db_url
        engine_kwargs = {"echo": False}
        if ":memory:" in url:
            from sqlalchemy.pool import StaticPool
            engine_kwargs["connect_args"] = {"check_same_thread": False}
            engine_kwargs["poolclass"] = StaticPool
        elif url.startswith("sqlite:///"):
            from pathlib import Path
            file_path = url.replace("sqlite:///", "")
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)

        self._engine = create_engine(url, **engine_kwargs)
        Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)

    # ── Write ─────────────────────────────────────────────────────

    def save_query(self, record: dict) -> int:
        """Persist a query record and return its auto-generated ID."""
        with self._Session() as session:  # type: Session
            obj = QueryRecord(**record)
            session.add(obj)
            session.commit()
            session.refresh(obj)
            logger.info(f"Saved query record #{obj.id}")
            return obj.id

    def update_feedback(
        self,
        query_id: int,
        feedback: str,
        corrected_sql: str | None = None,
    ) -> None:
        """Update user feedback for a previously saved query."""
        with self._Session() as session:  # type: Session
            record = session.get(QueryRecord, query_id)
            if record is None:
                logger.warning(f"Query #{query_id} not found for feedback update")
                return
            record.user_feedback = feedback
            if corrected_sql:
                record.corrected_sql = corrected_sql
            session.commit()
            logger.info(f"Updated feedback for query #{query_id}: {feedback}")

    # ── Read ──────────────────────────────────────────────────────

    def get_recent(self, limit: int = 20) -> list[QueryRecord]:
        """Return the *limit* most recent query records (newest first)."""
        with self._Session() as session:
            return (
                session.query(QueryRecord)
                .order_by(QueryRecord.created_at.desc())
                .limit(limit)
                .all()
            )

    def get_by_id(self, query_id: int) -> QueryRecord | None:
        """Return a single query record by ID."""
        with self._Session() as session:
            return session.get(QueryRecord, query_id)

    def get_successful_queries(self, limit: int = 50) -> list[QueryRecord]:
        """Return successful, positively-rated queries for few-shot seeding."""
        with self._Session() as session:
            return (
                session.query(QueryRecord)
                .filter(QueryRecord.was_successful.is_(True))
                .filter(QueryRecord.user_feedback == "positive")
                .order_by(QueryRecord.created_at.desc())
                .limit(limit)
                .all()
            )
