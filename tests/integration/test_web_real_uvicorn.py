"""Fast integration test: spawn real uvicorn via `kno serve`.

TestClient mounts the ASGI app in-process and never goes through uvicorn — so
it can't catch "uvicorn doesn't actually start," "the lifespan event raises,"
or "the entry point in pyproject is broken." This test boots the real
subprocess on a non-default port and curls it.

Cost: ~1-2s wall (subprocess boot + 2 HTTP calls + teardown). Keep it that way.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import Iterator

import httpx
import pytest

HOST = "127.0.0.1"
BOOT_TIMEOUT_S = 10.0


def _free_port() -> int:
    """Ask the OS for an unused port on HOST. Has a small TOCTOU window — the
    subprocess could lose the port to another listener between close and
    re-bind — acceptable for a single-developer-machine test."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


@pytest.fixture
def running_kno_serve() -> Iterator[str]:
    """Spawn ``uv run kno serve`` on a free port, yield BASE, terminate."""
    port = _free_port()
    base = f"http://{HOST}:{port}"
    env = os.environ.copy()
    env["KNO_HOST"] = HOST
    env["KNO_PORT"] = str(port)

    proc = subprocess.Popen(
        ["uv", "run", "kno", "serve"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        deadline = time.monotonic() + BOOT_TIMEOUT_S
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
                raise RuntimeError(f"kno serve exited early (rc={proc.returncode}): {stderr}")
            try:
                r = httpx.get(f"{base}/api/health", timeout=0.5)
                if r.status_code == 200:
                    break
            except httpx.RequestError:
                time.sleep(0.1)
        else:
            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            raise TimeoutError(f"kno serve did not bind {base} within {BOOT_TIMEOUT_S}s: {stderr}")

        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def test_real_uvicorn_serves_health(running_kno_serve: str) -> None:
    response = httpx.get(f"{running_kno_serve}/api/health")
    assert response.status_code == 200
    body = response.json()
    assert "anthropic" in body
    assert "google_oauth" in body
    assert "github_oauth" in body


def test_real_uvicorn_serves_ui_placeholder(running_kno_serve: str) -> None:
    response = httpx.get(f"{running_kno_serve}/ui/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Kno is running" in response.text
