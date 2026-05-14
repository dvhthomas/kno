"""Tests for the deploy config (`Dockerfile` + `fly.toml`).

Two layers:

- **Pure config-parse tests** run by default — `poe test-all` includes them.
- **Real-container tests** marked with `@pytest.mark.docker`; gated behind
  `poe test-docker` so the inner TDD loop stays fast. They actually invoke
  `docker build` + `docker run` and exercise `/api/health`.
"""

from __future__ import annotations

import pathlib
import shutil
import socket
import subprocess
import time
import tomllib
import uuid
from collections.abc import Iterator

import httpx
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        subprocess.run(
            ["docker", "info"], capture_output=True, check=True, timeout=5
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


def _free_port(host: str = "127.0.0.1") -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture
def fly_config() -> dict[str, object]:
    return tomllib.loads((REPO_ROOT / "fly.toml").read_text())


class TestFlyTomlShape:
    """The non-deploy-time bits of fly.toml are committed config — testable
    by reading the TOML and asserting structure. ``app`` and ``primary_region``
    are filled by `fly launch` at first deploy and are intentionally absent."""

    def test_internal_port_is_8080(self, fly_config):
        assert fly_config["http_service"]["internal_port"] == 8080

    def test_health_check_hits_api_health(self, fly_config):
        checks = fly_config["http_service"]["checks"]
        assert any(c.get("path") == "/api/health" for c in checks), (
            "expected at least one http_service.checks entry with path=/api/health"
        )

    def test_data_volume_mount_present(self, fly_config):
        mounts = fly_config["mounts"]
        assert any(m.get("destination") == "/data" for m in mounts), (
            "expected /data mount stub for future DB/KB milestones"
        )

    def test_force_https(self, fly_config):
        assert fly_config["http_service"]["force_https"] is True


@pytest.mark.docker
@pytest.mark.skipif(not _docker_available(), reason="docker daemon not available")
class TestContainerBehavior:
    """Real-container tests. Skipped unless `--strict-markers` + `poe test-docker`."""

    @pytest.fixture(scope="class")
    def image_tag(self) -> Iterator[str]:
        tag = f"kno-deploy-test:{uuid.uuid4().hex[:8]}"
        result = subprocess.run(
            ["docker", "build", "-t", tag, "."],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"docker build failed:\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        try:
            yield tag
        finally:
            subprocess.run(
                ["docker", "image", "rm", "-f", tag], capture_output=True, check=False
            )

    def test_image_builds(self, image_tag: str) -> None:
        # If the image_tag fixture didn't error, the build succeeded.
        assert image_tag.startswith("kno-deploy-test:")

    @pytest.fixture
    def running_container(self, image_tag: str) -> Iterator[str]:
        port = _free_port()
        base = f"http://127.0.0.1:{port}"
        # `docker run` itself may fail (bad image, port collision); use
        # check=False + explicit assertion so failure-before-try doesn't leak.
        proc = subprocess.run(
            [
                "docker", "run", "--rm", "-d",
                "-p", f"{port}:8080",
                "--name", f"kno-test-{port}",
                image_tag,
            ],
            capture_output=True, text=True, check=False,
        )
        assert proc.returncode == 0, f"docker run failed: {proc.stderr}"
        cid = proc.stdout.strip()
        try:
            # Poll /api/health for up to 15s; container needs ~1-2s to boot.
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    r = httpx.get(f"{base}/api/health", timeout=0.5)
                    if r.status_code == 200:
                        break
                except httpx.RequestError:
                    time.sleep(0.2)
            else:
                logs = subprocess.run(
                    ["docker", "logs", cid], capture_output=True, text=True, check=False
                )
                raise TimeoutError(
                    f"Container did not respond on {base}/api/health within 15s.\n"
                    f"docker logs:\n{logs.stdout}{logs.stderr}"
                )
            yield base
        finally:
            # 25s > uvicorn's --timeout-graceful-shutdown=20s so we don't race
            # the runtime budget on slow hosts.
            subprocess.run(
                ["docker", "stop", cid], capture_output=True, check=False, timeout=25
            )

    def test_health_returns_not_configured(self, running_container: str) -> None:
        response = httpx.get(f"{running_container}/api/health")
        assert response.status_code == 200
        body = response.json()
        assert body == {
            "anthropic": "not_configured",
            "google_oauth": "not_configured",
            "github_oauth": "not_configured",
        }

    def test_ui_root_serves_placeholder(self, running_container: str) -> None:
        response = httpx.get(f"{running_container}/ui/")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Kno is running" in response.text

    def test_image_under_size_budget(self, image_tag: str) -> None:
        """Guardrail: a careless dep addition shouldn't balloon the image past
        the budget. Current actual is ~101MB; 200MB leaves headroom for a
        few more deps but flags a runaway add (e.g., pulling in torch)."""
        result = subprocess.run(
            ["docker", "image", "inspect", image_tag, "--format", "{{.Size}}"],
            capture_output=True, text=True, check=True,
        )
        size_bytes = int(result.stdout.strip())
        budget_bytes = 200 * 1024 * 1024
        assert size_bytes < budget_bytes, (
            f"Image is {size_bytes / 1024 / 1024:.1f}MB; budget is "
            f"{budget_bytes / 1024 / 1024}MB. If this is intentional, raise the "
            f"budget here with a one-line justification commit."
        )
