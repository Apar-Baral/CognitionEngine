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
    try:
        app()
    except CognitionEngineError as exc:
        from src.cli import formatters

        formatters.print_error(exc.message, details=str(exc.details))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
