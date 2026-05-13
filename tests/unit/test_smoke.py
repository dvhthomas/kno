"""Smoke test: the package imports cleanly and reports a version.

Not TDD — a structural assertion that the project skeleton is wired correctly.
Per ``AGENTS.md``, Task 0.1 (project skeleton) is exempt from strict-TDD.
"""

from __future__ import annotations


def test_version_is_a_string() -> None:
    """The package exports a ``__version__`` string."""
    from kno import __version__

    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_cli_app_is_importable() -> None:
    """The Typer app imports — proves the ``[project.scripts]`` target resolves."""
    from kno.cli.main import app

    assert app is not None


def test_kno_version_subcommand_prints_version() -> None:
    """`kno version` exits 0 and prints the version string.

    Guards against Typer's single-command auto-collapse behavior: with only one
    subcommand registered, Typer promotes it to the top-level command unless a
    callback explicitly forces subcommand mode.
    """
    from typer.testing import CliRunner

    from kno import __version__
    from kno.cli.main import app

    runner = CliRunner()
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0, f"exit_code={result.exit_code}, output={result.output!r}"
    assert __version__ in result.output
