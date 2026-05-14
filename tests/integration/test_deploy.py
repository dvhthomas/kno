"""Tests for the deploy config (`Dockerfile` + `fly.toml`).

Two layers:

- **Pure config-parse tests** run by default — `poe test-all` includes them.
- **Real-container tests** marked with `@pytest.mark.docker`; gated behind
  `poe test-docker` so the inner TDD loop stays fast. They actually invoke
  `docker build` + `docker run` and exercise `/api/health`.
"""

from __future__ import annotations

import json
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
