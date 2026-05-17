"""Storage paths for memory subsystem."""

from __future__ import annotations

from pathlib import Path

from src.core.constants import COGNITION_DIR


def project_data_root(project_path: Path, project_name: str) -> Path:
    return project_path / "data" / "projects" / _safe_name(project_name)


def sessions_root(project_path: Path, project_name: str) -> Path:
    return project_data_root(project_path, project_name) / "sessions"


def metrics_db_path(project_path: Path, project_name: str) -> Path:
    return project_data_root(project_path, project_name) / "metrics" / "metrics.db"


def cognition_sessions_fallback(project_path: Path) -> Path:
    """Legacy/alternate path under .cognition/sessions."""
    return project_path / COGNITION_DIR / "sessions"


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
