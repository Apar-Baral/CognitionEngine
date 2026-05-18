"""Left sidebar markup — compact professional status."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def format_left_rail(
    *,
    project_root: Path,
    setup: dict[str, Any],
    project_setup: dict[str, Any],
    ctx: Any | None,
) -> str:
    proj = project_root.name or str(project_root)
    lines = [
        "[bold #58a6ff]COGNITION[/] [bold white]ENGINE[/]",
        "[dim]────────────────[/]",
        f"[bold]Project[/]  [white]{proj}[/]",
    ]
    if ctx and ctx.is_initialized():
        lines.append("[#3fb950]●[/] [dim]initialized[/]")
    else:
        lines.append("[#e3b341]○[/] [dim]run Setup keys[/]")

    model = ""
    key_line = "[dim]no API key[/]"
    if ctx:
        model = str(ctx.config.get("default_model", "—"))
        try:
            from src.cli.model_picker import resolve_model_id

            reg = ctx.model_registry()
            mid = resolve_model_id(model, reg) or model
            meta = reg.get_model(mid) or {}
            model = str(meta.get("display_name") or mid)
        except Exception:
            pass
        for prov in ("deepseek", "openai", "anthropic", "google", "openrouter"):
            if ctx.config.get_api_key(prov):
                key_line = f"[#3fb950]●[/] [white]{prov}[/]"
                break
    lines.extend(
        [
            "[dim]────────────────[/]",
            f"[bold]Model[/]   [cyan]{model}[/]",
            f"[bold]Key[/]     {key_line}",
        ]
    )
    gh = setup.get("github_repo") or project_setup.get("github_repo")
    if gh:
        lines.append(f"[bold]GitHub[/]  [dim]{gh}[/]")
    lines.append("[dim]────────────────[/]")
    return "\n".join(lines)
