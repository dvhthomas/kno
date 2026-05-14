"""Tests for the deploy config (`Dockerfile` + `fly.toml`).

Two layers:

- **Pure config-parse tests** run by default — `poe test-all` includes them.
- **Real-container tests** marked with `@pytest.mark.docker`; gated behind
  `poe test-docker` so the inner TDD loop stays fast. They actually invoke
  `docker build` + `docker run` and exercise `/api/health`.
"""

from __future__ import annotations

import pathlib
import tomllib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


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
