"""Integration tests for FastAPI endpoints."""

import io
import pytest
from fastapi.testclient import TestClient
from src.api.app import app
from src.config.settings import settings


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "dialect" in data
    assert "llm_provider" in data


def test_feedback_endpoint_supports_both_schemas(client):
    # Test with standard feedback payload
    res1 = client.post(
        "/api/v1/feedback",
        json={"query_id": 99999, "feedback": "positive"},
    )
    assert res1.status_code == 200

    # Test with Streamlit shorthand rating payload ('up' / 'down')
    res2 = client.post(
        "/api/v1/feedback",
        json={"query_id": 99999, "rating": "up"},
    )
    assert res2.status_code == 200

    res3 = client.post(
        "/api/v1/feedback",
        json={"query_id": 99999, "rating": "down"},
    )
    assert res3.status_code == 200


def test_db_test_connection_sqlite(client, tmp_path):
    db_file = tmp_path / "test.db"
    db_url = f"sqlite:///{db_file}"
    response = client.post(
        "/api/v1/db/test",
        json={"database_url": db_url},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["dialect"].lower() == "sqlite"


def test_db_upload_path_traversal_sanitized(client):
    fake_content = b"SQLite format 3\x00"
    # Filename with path traversal attempt
    response = client.post(
        "/api/v1/db/upload",
        files={"file": ("../../evil.db", io.BytesIO(fake_content), "application/x-sqlite3")},
    )
    # The file should be saved as evil.db inside user_uploads, not in parent directory
    if response.status_code == 200:
        data = response.json()
        assert "evil.db" in data["filename"]
        assert ".." not in data["filename"]


def test_query_request_does_not_mutate_global_settings(client, monkeypatch):
    original_db = settings.database_url
    original_provider = settings.llm_provider

    # Mock the pipeline invocation so we don't need real LLM keys for this test
    from src.api import routes
    mock_pipeline = routes._get_pipeline()
    monkeypatch.setattr(
        mock_pipeline,
        "invoke",
        lambda req: {
            "query_id": 1,
            "question": req["question"],
            "sql": "SELECT 1;",
            "results": [{"1": 1}],
            "raw_output": "1",
            "row_count": 1,
            "execution_time_ms": 1.0,
            "explanation": "Test",
            "confidence": 1.0,
            "refinement_count": 0,
            "success": True,
            "error": None,
        },
    )

    res = client.post(
        "/api/v1/query",
        json={
            "question": "Show all users",
            "database_url": "sqlite:///custom_isolated.db",
            "llm_provider": "gemini",
            "model": "gemini-2.0-flash",
            "api_key": "test_fake_key",
        },
    )
    assert res.status_code == 200

    # Ensure global settings were NOT overwritten by the per-request config
    assert settings.database_url == original_db
    assert settings.llm_provider == original_provider


def test_query_cache_hit_on_repeat(client, monkeypatch):
    from src.api import routes
    call_counter = {"count": 0}

    def fake_invoke(req):
        call_counter["count"] += 1
        return {
            "query_id": 42,
            "question": req["question"],
            "sql": "SELECT 42;",
            "results": [{"answer": 42}],
            "raw_output": "42",
            "row_count": 1,
            "execution_time_ms": 1.0,
            "explanation": "Answer is 42",
            "confidence": 1.0,
            "refinement_count": 0,
            "success": True,
            "error": None,
        }

    mock_pipeline = routes._get_pipeline()
    monkeypatch.setattr(mock_pipeline, "invoke", fake_invoke)

    # First call: executes pipeline and caches
    payload = {"question": "What is the meaning of life?", "database_url": "sqlite:///test_c.db"}
    res1 = client.post("/api/v1/query", json=payload)
    assert res1.status_code == 200
    assert call_counter["count"] == 1

    # Second identical call: hits cache, pipeline is not called again!
    res2 = client.post("/api/v1/query", json=payload)
    assert res2.status_code == 200
    assert call_counter["count"] == 1  # Still 1! Cache served it
    data2 = res2.json()
    assert "Instant Cache Hit" in data2["explanation"]


def test_query_stream_sse_endpoint(client):
    payload = {"question": "List 5 items", "database_url": "sqlite:///test_s.db"}
    response = client.post("/api/v1/query/stream", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")


def test_rate_limiter_headers_present(client):
    response = client.get("/api/v1/history")
    assert response.status_code == 200
    assert "x-ratelimit-remaining" in response.headers

