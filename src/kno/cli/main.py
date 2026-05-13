"""Kno CLI entry point.

``pyproject.toml [project.scripts]`` exposes this as the ``kno`` command after
``uv sync`` (and on ``$PATH`` after ``uv tool install -e .``).
"""

from __future__ import annotations

import typer
import uvicorn

from kno import __version__
from kno.config import Settings

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


@app.command()
def serve() -> None:
    """Run the Kno web shell (FastAPI app behind uvicorn).

    Host/port come from ``Settings`` so ``KNO_HOST`` / ``KNO_PORT`` env vars
    override the defaults (``0.0.0.0:8000``).
    """
    settings = Settings()
    uvicorn.run("kno.web.app:app", host=settings.host, port=settings.port)


if __name__ == "__main__":
    app()
