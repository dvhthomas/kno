"""Kno configuration — lenient-boot Settings.

Per ``docs/ops.md`` §0 and ADR-0018 §2.3 item 11: the server must boot cleanly
with no secrets set, so the Hello-Kno milestone deploy is reachable without
any OAuth registrations or API keys. Required-for-normal-operation secrets are
optional fields here and reported as ``not_configured`` by ``/api/health``
(added in Task 0.10); they are *not* boot-blocking errors.

Settings sources, in pydantic-settings priority order:

1. Environment variables prefixed with ``KNO_`` (e.g. ``KNO_PORT=8001``).
2. A ``.env`` file in the current directory (lower priority than process env).
3. Defaults declared on the fields below.
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Kno settings. Instantiated once at server start; injected via FastAPI deps."""

    model_config = SettingsConfigDict(
        env_prefix="KNO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Bootstrap (always populated; have defaults) ────────────────────────
    host: str = "0.0.0.0"  # binds 0.0.0.0 by design (container deploy)
    port: int = 8000

    # ── Identity (not secret) ──────────────────────────────────────────────
    admin_email: str | None = None

    # ── Encryption + session (secret; consumed by auth layer) ──────────────
    token_enc_key: SecretStr | None = None
    session_secret: SecretStr | None = None

    # ── OAuth — client IDs are public; client secrets are SecretStr ───────
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    github_client_id: str | None = None
    github_client_secret: SecretStr | None = None

    # ── LLM provider (API key is secret) ───────────────────────────────────
    anthropic_api_key: SecretStr | None = None

    # ── Observability (optional in every mode; key is secret) ──────────────
    honeycomb_key: SecretStr | None = None

    @property
    def providers_status(self) -> dict[str, bool]:
        """Per-provider configured-or-not, for ``/api/health`` to surface.

        OAuth providers require BOTH client_id and client_secret — a half-set
        is "not configured" because the OAuth flow would fail anyway.
        """
        return {
            "anthropic": self.anthropic_api_key is not None,
            "google_oauth": (
                self.google_client_id is not None
                and self.google_client_secret is not None
            ),
            "github_oauth": (
                self.github_client_id is not None
                and self.github_client_secret is not None
            ),
        }
