"""
CLI entry point for Cognition Engine (`cc` / `cognition-engine`).
"""

from __future__ import annotations

import logging
import signal
import sys

from src.cli.commands import app
from src.core.exceptions import CognitionEngineError


def _shutdown_handler(signum: int, frame: object) -> None:
    _ = signum, frame
    print("\nShutting down Cognition Engine...")
    sys.exit(0)


signal.signal(signal.SIGINT, _shutdown_handler)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _shutdown_handler)


def main() -> None:
    from src.core.env_guard import reexec_in_cognition_venv

    reexec_in_cognition_venv()

    # No subcommand → interactive REPL (Hermes-style default)
    if len(sys.argv) == 1:
        from src.cli.interactive_setup import ensure_interactive_ready
        from src.repl.repl_app import run_repl_textual

        ensure_interactive_ready(interactive=True)
        run_repl_textual()
        return
    try:
        app()
    except CognitionEngineError as exc:
        from src.cli import formatters

        formatters.print_error(exc.message, details=str(exc.details))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
