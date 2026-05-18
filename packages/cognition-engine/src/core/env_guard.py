"""Ensure Cognition Engine runs inside its venv (Hermes-style — no PEP 668 surprises)."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_venv_active() -> bool:
    """True when running inside any virtual environment."""
    if sys.prefix != sys.base_prefix:
        return True
    return bool(getattr(sys, "real_prefix", None))


def cognition_engine_home() -> Path:
    return Path(os.environ.get("COGNITION_ENGINE_HOME", Path.home() / "CognitionEngine")).expanduser()


def cognition_venv_python() -> Path | None:
    """Path to CE package venv python, if install-ce.sh layout exists."""
    pkg = cognition_engine_home() / "packages" / "cognition-engine"
    for rel in ("bin/python", "Scripts/python.exe"):
        candidate = pkg / ".venv" / rel
        if candidate.is_file():
            return candidate.resolve()
    return None


def reexec_in_cognition_venv() -> None:
    """
    Re-launch this process with the CE venv interpreter when available.
    Avoids Kali/system PEP 668 errors without asking the user to activate manually.
    """
    if is_venv_active():
        return
    if os.environ.get("CE_SKIP_VENV_REEXEC") == "1":
        return
    venv_py = cognition_venv_python()
    if venv_py is None:
        return
    try:
        if Path(sys.executable).resolve() == venv_py:
            return
    except OSError:
        return
    os.environ["CE_SKIP_VENV_REEXEC"] = "1"
    os.execv(str(venv_py), [str(venv_py), *sys.argv])


def runtime_env_status() -> dict[str, str | bool]:
    """Diagnostics for doctor / REPL status bar."""
    venv_py = cognition_venv_python()
    return {
        "venv_active": is_venv_active(),
        "ce_venv_found": venv_py is not None,
        "ce_venv_python": str(venv_py) if venv_py else "",
        "executable": sys.executable,
        "recommended_activate": (
            f"source {venv_py.parent}/activate"
            if venv_py and venv_py.parent.name == "bin"
            else ""
        ),
    }


def env_warning_message() -> str | None:
    """Human-readable warning when env is risky; None if OK."""
    if is_venv_active():
        return None
    venv_py = cognition_venv_python()
    if venv_py:
        return (
            "Not in a virtualenv. CE will auto-switch when started from system Python.\n"
            f"Or activate: source {venv_py.parent}/activate"
        )
    return (
        "Not in a virtualenv and CE is not installed under ~/CognitionEngine.\n"
        "Run: curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/"
        "master/scripts/install-ce.sh | bash"
    )
