"""Tests for the query history database."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, QueryRecord
from src.db.history import QueryHistory


@pytest.fixture
def history(tmp_path):
    """QueryHistory backed by a temp SQLite database."""
    db_url = f"sqlite:///{tmp_path / 'test_history.db'}"
    return QueryHistory(db_url=db_url)


@pytest.fixture
def sample_record():
    return {
        "question": "How many customers are there?",
        "generated_sql": "SELECT COUNT(*) FROM customers;",
        "final_sql": "SELECT COUNT(*) FROM customers;",
        "results_preview": "[{'row': 0, 'data': (500,)}]",
        "row_count": 1,
        "execution_time_ms": 12.5,
        "was_successful": True,
        "confidence": 0.95,
        "refinement_count": 0,
        "explanation": "Counts all rows in the customers table.",
    }


class TestQueryHistory:
    def test_save_and_retrieve(self, history, sample_record):
        query_id = history.save_query(sample_record)
        assert query_id > 0

        records = history.get_recent(limit=5)
        assert len(records) == 1
        assert records[0].question == sample_record["question"]

    def test_update_feedback(self, history, sample_record):
        query_id = history.save_query(sample_record)
        history.update_feedback(query_id, "positive")

        record = history.get_by_id(query_id)
        assert record.user_feedback == "positive"

    def test_update_feedback_with_correction(self, history, sample_record):
        query_id = history.save_query(sample_record)
        corrected = "SELECT COUNT(DISTINCT id) FROM customers;"
        history.update_feedback(query_id, "corrected", corrected)

        record = history.get_by_id(query_id)
        assert record.user_feedback == "corrected"
        assert record.corrected_sql == corrected

    def test_get_successful_queries(self, history, sample_record):
        # Save a successful query with positive feedback
        query_id = history.save_query(sample_record)
        history.update_feedback(query_id, "positive")

        successful = history.get_successful_queries(limit=10)
        assert len(successful) == 1

    def test_get_recent_ordering(self, history):
        """Newest queries should appear first."""
        for i in range(5):
            history.save_query({
                "question": f"Question {i}",
                "generated_sql": f"SELECT {i};",
                "final_sql": f"SELECT {i};",
                "was_successful": True,
                "confidence": 0.9,
                "refinement_count": 0,
            })

        records = history.get_recent(limit=3)
        assert len(records) == 3
        # Most recent question should be last one saved
        assert records[0].question == "Question 4"

    def test_nonexistent_feedback(self, history):
        """Updating feedback for a missing ID should not crash."""
        history.update_feedback(99999, "positive")  # should not raise
