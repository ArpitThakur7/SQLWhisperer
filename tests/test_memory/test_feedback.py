"""Tests for user feedback handler and learning loop."""

import pytest
from unittest.mock import MagicMock
from src.memory.feedback import FeedbackHandler
from src.db.history import QueryHistory


@pytest.fixture
def mock_few_shot_store():
    store = MagicMock()
    return store


@pytest.fixture
def history(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'feedback_test.db'}"
    return QueryHistory(db_url=db_url)


def test_positive_feedback_learns_example(history, mock_few_shot_store):
    query_id = history.save_query({
        "question": "What is total sales?",
        "generated_sql": "SELECT SUM(amount) FROM sales;",
        "final_sql": "SELECT SUM(amount) FROM sales;",
        "was_successful": True,
        "explanation": "Sums total sales amount.",
    })

    handler = FeedbackHandler(few_shot_store=mock_few_shot_store, history=history)
    res = handler.handle_feedback(query_id=query_id, feedback="positive")

    assert res["status"] == "ok"
    mock_few_shot_store.add_example.assert_called_once_with(
        question="What is total sales?",
        sql="SELECT SUM(amount) FROM sales;",
        explanation="Sums total sales amount.",
        source="positive_feedback",
    )


def test_corrected_feedback_learns_correction(history, mock_few_shot_store):
    query_id = history.save_query({
        "question": "Find users",
        "generated_sql": "SELECT * FROM usr;",
        "final_sql": "SELECT * FROM usr;",
        "was_successful": False,
    })

    handler = FeedbackHandler(few_shot_store=mock_few_shot_store, history=history)
    res = handler.handle_feedback(
        query_id=query_id,
        feedback="corrected",
        corrected_sql="SELECT * FROM users;",
    )

    assert res["status"] == "ok"
    mock_few_shot_store.add_example.assert_called_once_with(
        question="Find users",
        sql="SELECT * FROM users;",
        explanation="User-corrected query",
        source="correction",
    )


def test_negative_feedback_does_not_add_example(history, mock_few_shot_store):
    query_id = history.save_query({
        "question": "Bad query",
        "generated_sql": "SELECT 1;",
        "final_sql": "SELECT 1;",
        "was_successful": True,
    })

    handler = FeedbackHandler(few_shot_store=mock_few_shot_store, history=history)
    res = handler.handle_feedback(query_id=query_id, feedback="negative")

    assert res["status"] == "ok"
    mock_few_shot_store.add_example.assert_not_called()
