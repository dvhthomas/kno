"""Tests for ``kno.config`` — the lenient-boot Settings contract.

Per ``docs/ops.md`` §0 and ADR-0018 §2.3 item 11: the server must boot cleanly
with no secrets set, so the Hello-Kno milestone deploy is reachable without
any OAuth registrations or API keys. Missing optional secrets are reported as
``not_configured`` by ``/api/health`` (added in Task 0.10); they are *not*
boot-blocking errors.
"""

from __future__ import annotations

import pytest


def test_settings_boots_with_no_env_vars_set(no_kno_env: None) -> None:
    """``Settings()`` does not raise when no env vars are set.

    Load-bearing per ``docs/ops.md`` §0 — Hello-Kno deploy must work without
    any provider credentials.
    """
    from kno.config import Settings

    settings = Settings()

    # Bootstrap fields have sensible defaults so the FastAPI server can start.
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000


def test_optional_credential_fields_default_to_None(no_kno_env: None) -> None:
    """Every required-for-normal-operation credential is ``None`` when absent.

    The contract is "boot anyway and report as not_configured", not "crash on
    missing secret." Verified per provider so a future field-name typo is
    caught here, not at deploy time.
    """
    from kno.config import Settings

    settings = Settings()

    # Identity
    assert settings.admin_email is None

    # Encryption + session secrets (consumed by the auth layer)
    assert settings.token_enc_key is None
    assert settings.session_secret is None

    # OAuth client credentials
    assert settings.google_client_id is None
    assert settings.google_client_secret is None
    assert settings.github_client_id is None
    assert settings.github_client_secret is None

    # LLM provider key
    assert settings.anthropic_api_key is None

    # Observability (optional in every mode)
    assert settings.honeycomb_key is None


def test_sensitive_fields_use_SecretStr_and_dont_leak_in_repr(
    no_kno_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Credential fields are ``SecretStr``-wrapped so values don't leak.

    ``SecretStr`` overrides ``__repr__`` to show ``**********`` instead of the
    underlying value. Use ``.get_secret_value()`` when the actual string is
    needed (e.g. when calling an external API). The `kno_token_enc_key`,
    `kno_session_secret`, and OAuth client secrets are the same pattern.
    """
    from pydantic import SecretStr

    monkeypatch.setenv("KNO_ANTHROPIC_API_KEY", "sk-ant-test-secret-value")
    monkeypatch.setenv("KNO_TOKEN_ENC_KEY", "kek-test-value")
    monkeypatch.setenv("KNO_SESSION_SECRET", "session-test-value")
    monkeypatch.setenv("KNO_GOOGLE_CLIENT_SECRET", "goauth-test-value")
    monkeypatch.setenv("KNO_GITHUB_CLIENT_SECRET", "ghub-test-value")
    monkeypatch.setenv("KNO_HONEYCOMB_KEY", "honeycomb-test-value")

    from kno.config import Settings

    settings = Settings()

    # All sensitive fields are SecretStr-wrapped.
    assert isinstance(settings.anthropic_api_key, SecretStr)
    assert isinstance(settings.token_enc_key, SecretStr)
    assert isinstance(settings.session_secret, SecretStr)
    assert isinstance(settings.google_client_secret, SecretStr)
    assert isinstance(settings.github_client_secret, SecretStr)
    assert isinstance(settings.honeycomb_key, SecretStr)

    # The real value is accessible via .get_secret_value().
    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-test-secret-value"

    # The value never appears in repr() of the field or the whole Settings.
    assert "sk-ant-test-secret-value" not in repr(settings.anthropic_api_key)
    assert "sk-ant-test-secret-value" not in repr(settings)
    assert "kek-test-value" not in repr(settings)
    assert "session-test-value" not in repr(settings)


def test_providers_status_reports_per_provider(
    no_kno_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``providers_status`` reports each provider's configured-ness.

    Used by ``/api/health`` (Task 0.10) to surface ``provider: ok`` vs
    ``provider: not_configured``. OAuth providers require BOTH ``client_id``
    and ``client_secret`` to count as configured — a half-set is no better
    than absent.
    """
    from kno.config import Settings

    # When no env vars are set, every provider reports not-configured.
    settings_empty = Settings()
    assert settings_empty.providers_status == {
        "anthropic": False,
        "google_oauth": False,
        "github_oauth": False,
    }

    # When every required env var is set, every provider reports configured.
    monkeypatch.setenv("KNO_ANTHROPIC_API_KEY", "sk-ant-xyz")
    monkeypatch.setenv("KNO_GOOGLE_CLIENT_ID", "google-id")
    monkeypatch.setenv("KNO_GOOGLE_CLIENT_SECRET", "google-secret")
    monkeypatch.setenv("KNO_GITHUB_CLIENT_ID", "github-id")
    monkeypatch.setenv("KNO_GITHUB_CLIENT_SECRET", "github-secret")

    settings_full = Settings()
    assert settings_full.providers_status == {
        "anthropic": True,
        "google_oauth": True,
        "github_oauth": True,
    }

    # OAuth providers need BOTH id and secret. Missing one is still
    # "not configured" — partial credentials would fail at OAuth-flow time
    # anyway.
    monkeypatch.delenv("KNO_GOOGLE_CLIENT_SECRET")
    settings_partial = Settings()
    assert settings_partial.providers_status["google_oauth"] is False, (
        "google_oauth requires BOTH client_id and client_secret"
    )
