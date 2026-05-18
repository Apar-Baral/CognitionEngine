"""Interactive model selection (CLI setup + REPL)."""

from __future__ import annotations

from typing import Any

from src.cli import prompts
from src.models.dynamic_registry import DynamicRegistry, ensure_models_yaml
from src.core.constants import MODELS_REGISTRY_PATH


def registry_model_options(
    reg: DynamicRegistry | None = None,
    *,
    limit: int = 30,
) -> list[dict[str, str]]:
    reg = reg or DynamicRegistry(ensure_models_yaml())
    options: list[dict[str, str]] = []
    for mid in reg.list_models()[:limit]:
        meta = reg.get_model(mid) or {}
        tier = meta.get("tier", "?")
        name = meta.get("display_name") or mid
        provider = meta.get("provider", "")
        options.append(
            {
                "value": mid,
                "name": f"{mid}",
                "description": f"{name} · {tier} · {provider}",
            }
        )
    return options


def prompt_select_model(
    *,
    default_id: str | None = None,
    interactive: bool = True,
) -> str:
    """Numbered picker like Hermes; falls back to default or first model."""
    reg = DynamicRegistry(ensure_models_yaml())
    options = registry_model_options(reg)
    if not options:
        return default_id or "claude-sonnet-4-20250514"
    if not interactive:
        if default_id and default_id in reg.list_models():
            return default_id
        default = reg.get_default_model()
        return str(default["id"]) if default else options[0]["value"]

    # Pre-select current default in list
    default_idx = 1
    if default_id:
        for i, opt in enumerate(options, 1):
            if opt["value"] == default_id:
                default_idx = i
                break

    prompts.console.print("[bold cyan]Select default model[/bold cyan]")
    for i, opt in enumerate(options, 1):
        mark = " [green]← current[/green]" if opt["value"] == default_id else ""
        prompts.console.print(
            f"  {i}. {opt['name']} [dim]— {opt.get('description', '')}[/dim]{mark}"
        )
    try:
        from rich.prompt import IntPrompt

        choice = IntPrompt.ask("Choose model number", default=default_idx)
        idx = max(1, min(len(options), choice)) - 1
        return options[idx]["value"]
    except (KeyboardInterrupt, EOFError):
        if default_id:
            return default_id
        return options[0]["value"]


def format_models_table(reg: DynamicRegistry, *, limit: int = 25) -> str:
    lines = ["[bold]ID[/] · [bold]Name[/] · [bold]Tier[/] · [bold]Provider[/]"]
    for mid in reg.list_models()[:limit]:
        m = reg.get_model(mid) or {}
        lines.append(
            f"[cyan]{mid}[/] · {m.get('display_name', mid)} · "
            f"{m.get('tier', '?')} · {m.get('provider', '?')}"
        )
    rest = len(reg.list_models()) - limit
    if rest > 0:
        lines.append(f"[dim]… and {rest} more (use /model ID)[/dim]")
    return "\n".join(lines)
