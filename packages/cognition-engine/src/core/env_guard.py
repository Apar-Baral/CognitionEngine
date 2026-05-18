"""Hermes-style: always run CE on its own venv — never ask user to activate."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def cognition_engine_home() -> Path:
    return Path(os.environ.get("COGNITION_ENGINE_HOME", Path.home() / "CognitionEngine")).expanduser()


def ce_venv_dir() -> Path | None:
    """CE virtualenv root (works when bin/python symlinks to /usr/bin/python3)."""
    d = cognition_engine_home() / "packages" / "cognition-engine" / ".venv"
    return d.resolve() if d.is_dir() else None


def cognition_venv_python() -> Path | None:
    venv = ce_venv_dir()
    if not venv:
        return None
    for rel in ("bin/python", "bin/python3", "Scripts/python.exe"):
        candidate = venv / rel
        if candidate.exists():
            return candidate
    return None


def cognition_venv_bin() -> Path | None:
    venv = ce_venv_dir()
    return (venv / "bin") if venv and (venv / "bin").is_dir() else None


def is_running_on_ce_venv() -> bool:
    """True when sys.prefix is the CE venv (reliable on Kali symlinked pythons)."""
    venv_dir = ce_venv_dir()
    if not venv_dir:
        return False
    try:
        return Path(sys.prefix).resolve() == venv_dir
    except OSError:
        return False


def is_venv_active() -> bool:
    if sys.prefix != sys.base_prefix:
        return True
    return bool(getattr(sys, "real_prefix", None))


def reexec_in_cognition_venv() -> None:
    """Re-launch with CE venv (even if another project .venv is active)."""
    if os.environ.get("CE_SKIP_VENV_REEXEC") == "1":
        return
    venv_py = cognition_venv_python()
    if not venv_py:
        return
    if is_running_on_ce_venv():
        return
    venv_dir = ce_venv_dir()
    os.environ["CE_SKIP_VENV_REEXEC"] = "1"
    if venv_dir:
        os.environ["VIRTUAL_ENV"] = str(venv_dir)
    os.execv(str(venv_py), [str(venv_py), *sys.argv])


def runtime_env_status() -> dict[str, str | bool]:
    venv_dir = ce_venv_dir()
    venv_py = cognition_venv_python()
    on_ce = is_running_on_ce_venv()
    display = str(venv_dir) if on_ce and venv_dir else (str(venv_py) if venv_py else "")
    return {
        "venv_active": is_venv_active(),
        "ce_venv_active": on_ce,
        "ce_venv_found": venv_dir is not None,
        "ce_venv_dir": str(venv_dir) if venv_dir else "",
        "ce_venv_python": display,
        "executable": sys.executable,
        "python_prefix": sys.prefix,
    }


def env_warning_message() -> str | None:
    if is_running_on_ce_venv() or cognition_venv_python():
        return None
    return (
        "Cognition Engine not installed. Run:\n"
        "  curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/"
        "master/scripts/install-ce.sh | bash"
    )
