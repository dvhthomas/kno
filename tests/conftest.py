"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture
def no_kno_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear every ``KNO_*`` and ``DATABASE_URL`` env var so ``Settings()``
    sees only defaults — required for reproducible defaults assertions."""
    for key in list(os.environ):
        if key.startswith("KNO_") or key == "DATABASE_URL":
            monkeypatch.delenv(key)
    yield
