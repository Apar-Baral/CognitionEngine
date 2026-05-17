"""CLI entry point for Cognition Engine (`cc` / `cognition-engine`)."""

from __future__ import annotations

import typer
from rich.console import Console

app = typer.Typer(
    name="cc",
    help="Cognition Engine — AI development orchestrator",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def main() -> None:
    """Cognition Engine CLI."""


@app.command("version")
def version() -> None:
    """Show installed version."""
    from src import __version__

    console.print(f"cognition-engine {__version__}")


if __name__ == "__main__":
    app()
