"""Tests for the ``kno serve`` subcommand (issue #1)."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner


def test_serve_invokes_uvicorn_with_app_host_and_port(
    no_kno_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`kno serve` calls ``uvicorn.run`` with the FastAPI app and Settings host/port.

    The CLI is a thin wrapper around ``uvicorn.run``; the unit test mocks it
    so the subprocess never actually starts. The fast integration test in
    ``test_web_integration.py`` covers the real boot path.
    """
    import uvicorn

    captured: dict[str, Any] = {}

    def fake_run(app: Any, **kwargs: Any) -> None:
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", fake_run)

    from kno.cli.main import app as cli_app

    result = CliRunner().invoke(cli_app, ["serve"])

    assert result.exit_code == 0, result.output
    assert captured["app"] == "kno.web.app:app"
    assert captured["kwargs"]["host"] == "0.0.0.0"
    assert captured["kwargs"]["port"] == 8000
