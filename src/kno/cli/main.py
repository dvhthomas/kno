"""Kno CLI entry point.

``pyproject.toml [project.scripts]`` exposes this as the ``kno`` command after
``uv sync`` (and on ``$PATH`` after ``uv tool install -e .``).
"""

from __future__ import annotations

import typer

from kno import __version__

app = typer.Typer(
    name="kno",
    help="Personal agent harness.",
    no_args_is_help=True,
)


@app.callback()
def _root() -> None:
    """Personal agent harness.

    The callback forces Typer to treat subcommands as required instead of
    collapsing a single ``@app.command()`` into the top-level command. More
    subcommands land alongside ``version`` in later tasks (e.g. ``serve``,
    ``backup``, ``restore``).
    """


@app.command()
def version() -> None:
    """Print the installed Kno version."""
    typer.echo(f"kno {__version__}")


if __name__ == "__main__":
    app()
