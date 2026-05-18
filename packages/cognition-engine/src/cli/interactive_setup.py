"""First launch helper — delegates to Baral quick setup (single pass)."""

from __future__ import annotations

import os
from pathlib import Path

from src.cli.context import ProjectContext, resolve_project_root
from src.cli.baral_setup import baral_quick_setup, needs_quick_setup


def ensure_interactive_ready(
    project_root: Path | None = None,
    *,
    interactive: bool = True,
) -> ProjectContext:
    """One-time key setup if needed; never prompts twice per process."""
    if os.environ.get("CE_SKIP_SETUP") == "1":
        return ProjectContext(resolve_project_root(project_root))

    if os.environ.get("CE_SETUP_DONE") == "1":
        return ProjectContext(resolve_project_root(project_root))

    root = resolve_project_root(project_root)
    if interactive and needs_quick_setup():
        ctx = baral_quick_setup(root, ask_keys=True, ask_model=True, init_project=False)
        os.environ["CE_SETUP_DONE"] = "1"
        return ctx

    os.environ["CE_SETUP_DONE"] = "1"
    return ProjectContext(root)


def run_quick_setup_in_terminal(project_root: Path | None = None) -> None:
    from src.cli.baral_setup import baral_quick_setup

    baral_quick_setup(project_root or Path.cwd(), ask_keys=True, init_project=True)
