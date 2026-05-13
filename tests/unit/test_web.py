"""Tests for the FastAPI web shell (issue #1)."""

from fastapi.testclient import TestClient


def test_health_returns_200() -> None:
    from kno.web.app import app

    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200
