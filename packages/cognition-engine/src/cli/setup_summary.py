"""Persist and display last setup choices (shown in REPL sidebar)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.core.constants import COGNITION_DIR

LAST_SETUP_GLOBAL = "~/.cognition/last_setup.yaml"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_last_setup() -> dict[str, Any]:
    path = Path(LAST_SETUP_GLOBAL).expanduser()
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def save_last_setup(data: dict[str, Any]) -> Path:
    path = Path(LAST_SETUP_GLOBAL).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**load_last_setup(), **data, "updated_at": _now_iso()}
    path.write_text(yaml.safe_dump(merged, default_flow_style=False), encoding="utf-8")
    return path


def save_project_setup_summary(project_root: Path, data: dict[str, Any]) -> Path:
    path = project_root / COGNITION_DIR / "setup_summary.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = {**data, "updated_at": _now_iso()}
    path.write_text(yaml.safe_dump(merged, default_flow_style=False), encoding="utf-8")
    return path


def load_project_setup_summary(project_root: Path) -> dict[str, Any]:
    path = project_root / COGNITION_DIR / "setup_summary.yaml"
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def format_setup_summary_rich(
    global_data: dict[str, Any] | None = None,
    project_data: dict[str, Any] | None = None,
    *,
    ctx: Any | None = None,
) -> str:
    """Markup string for REPL setup panel."""
    g = global_data or {}
    p = project_data or {}
    lines = ["[bold #58a6ff]Setup[/]"]
    model = p.get("default_model") or g.get("default_model") or "—"
    lines.append(f"[dim]Model[/]  [white]{model}[/]")
    proj = p.get("project_path") or g.get("project_path") or "—"
    lines.append(f"[dim]Project[/] [white]{proj}[/]")
    git = p.get("git_initialized", g.get("git_initialized"))
    gh = p.get("github_push", g.get("github_push", "—"))
    lines.append(f"[dim]Git[/]     [white]{'yes' if git else 'no'}[/]  [dim]GitHub[/] [white]{gh}[/]")
    if ctx is not None:
        from src.cli.api_key_providers import format_active_key_status

        model_id = str(ctx.config.get("default_model") or model)
        lines.append(format_active_key_status(ctx.config, model_id))
    else:
        keys_display = g.get("api_keys_display") or p.get("api_keys_display")
        if not keys_display:
            from src.cli.api_key_providers import format_configured_keys

            model_for_keys = str(model) if model != "—" else ""
            keys_display = format_configured_keys(
                g.get("api_keys_configured") or [], model_id=model_for_keys
            )
        if keys_display:
            lines.append(f"[dim]API keys[/] [white]{keys_display}[/]")
    install = g.get("install_type", "slim")
    lines.append(f"[dim]Install[/] [white]{install}[/]")
    goal = p.get("goal_preview") or ""
    if goal:
        preview = goal if len(goal) <= 48 else goal[:45] + "…"
        lines.append(f"[dim]Goal[/]    [white]{preview}[/]")
    return "\n".join(lines)
