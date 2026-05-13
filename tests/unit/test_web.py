"""Tests for the FastAPI web shell (issue #1)."""

from fastapi.testclient import TestClient


def test_health_returns_200() -> None:
    from kno.web.app import app

    client = TestClient(app)
    response = client.get("/api/health")

    assert response.status_code == 200


def test_ui_root_returns_html_placeholder() -> None:
    """`GET /ui/` returns a placeholder HTML page until the setup wizard exists.

    Per `docs/ops.md` §1: 'Kno is running; setup not yet completed.' is what
    a visitor sees at the Hello-Kno milestone.
    """
    from kno.web.app import app

    client = TestClient(app)
    response = client.get("/ui/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Kno is running" in response.text


def test_health_reports_providers_not_configured_when_no_secrets(
    no_kno_env: None,
) -> None:
    """With no credentials configured, every provider reports `not_configured`.

    The string form (vs the bool from ``providers_status``) is what surfaces
    in the health payload, per ``docs/ops.md`` §1 Milestone 1 expected output.
    """
    from kno.web.app import app

    client = TestClient(app)
    response = client.get("/api/health")
    body = response.json()

    assert body["anthropic"] == "not_configured"
    assert body["google_oauth"] == "not_configured"
    assert body["github_oauth"] == "not_configured"
