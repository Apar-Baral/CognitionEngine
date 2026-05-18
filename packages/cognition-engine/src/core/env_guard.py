"""Hermes-style: always run CE on its own venv — never ask user to activate."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def cognition_engine_home() -> Path:
    return Path(os.environ.get("COGNITION_ENGINE_HOME", Path.home() / "CognitionEngine")).expanduser()


def cognition_venv_python() -> Path | None:
    pkg = cognition_engine_home() / "packages" / "cognition-engine"
    for rel in ("bin/python", "Scripts/python.exe"):
        candidate = pkg / ".venv" / rel
        if candidate.is_file():
            return candidate.resolve()
    return None


def cognition_venv_bin() -> Path | None:
    py = cognition_venv_python()
    return py.parent if py else None


def is_running_on_ce_venv() -> bool:
    venv_py = cognition_venv_python()
    if not venv_py:
        return False
    try:
        return Path(sys.executable).resolve() == venv_py
    except OSError:
        return False


def is_venv_active() -> bool:
    if sys.prefix != sys.base_prefix:
        return True
    return bool(getattr(sys, "real_prefix", None))


def reexec_in_cognition_venv() -> None:
    """
    Re-launch with CE's venv Python.
    Runs even if another project venv is active (fixes Kali xss-finder .venv + CE).
    """
    if os.environ.get("CE_SKIP_VENV_REEXEC") == "1":
        return
    venv_py = cognition_venv_python()
    if not venv_py:
        return
    if is_running_on_ce_venv():
        return
    os.environ["CE_SKIP_VENV_REEXEC"] = "1"
    os.environ["VIRTUAL_ENV"] = str(venv_py.parent.parent)
    os.execv(str(venv_py), [str(venv_py), *sys.argv])


def ensure_path_in_shell() -> str | None:
    """Return export line for ~/.bashrc if CE bin not on PATH."""
    bin_dir = cognition_venv_bin()
    if not bin_dir:
        return None
    ce = bin_dir / "cognition-engine"
    if not ce.is_file():
        return None
    return f'export PATH="{bin_dir}:$PATH"'


def runtime_env_status() -> dict[str, str | bool]:
    venv_py = cognition_venv_python()
    on_ce = is_running_on_ce_venv()
    return {
        "venv_active": is_venv_active(),
        "ce_venv_active": on_ce,
        "ce_venv_found": venv_py is not None,
        "ce_venv_python": str(venv_py) if venv_py else "",
        "executable": sys.executable,
    }


def env_warning_message() -> str | None:
    if is_running_on_ce_venv():
        return None
    venv_py = cognition_venv_python()
    if venv_py:
        return None  # reexec handles it; no warning needed
    return (
        "Cognition Engine not installed. Run:\n"
        "  curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/"
        "master/scripts/install-ce.sh | bash"
    )
