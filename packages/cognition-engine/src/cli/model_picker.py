"""Interactive model selection (CLI setup + REPL)."""

from __future__ import annotations

from typing import Any

from src.cli import prompts
from src.core.constants import MODELS_REGISTRY_PATH
from src.models.dynamic_registry import DynamicRegistry, ensure_models_yaml

TIER_ORDER = ("premium", "standard", "economy")
TIER_LABELS = {
    "premium": "Premium",
    "standard": "Standard",
    "economy": "Economy",
}


def registry_model_options(
    reg: DynamicRegistry | None = None,
    *,
    limit: int = 30,
    tier: str | None = None,
    query: str = "",
) -> list[dict[str, str]]:
    reg = reg or DynamicRegistry(ensure_models_yaml())
    options: list[dict[str, str]] = []
    q = query.strip().lower()
    for mid in reg.list_models():
        meta = reg.get_model(mid) or {}
        if tier and meta.get("tier") != tier:
            continue
        name = str(meta.get("display_name") or mid)
        provider = str(meta.get("provider") or "")
        blob = f"{mid} {name} {provider} {meta.get('tier', '')}".lower()
        if q and q not in blob:
            continue
        tier_key = str(meta.get("tier") or "?")
        options.append(
            {
                "value": mid,
                "name": mid,
                "display_name": name,
                "tier": tier_key,
                "provider": provider,
                "description": f"{name} · {tier_key} · {provider}",
                "select_label": f"{name}  ({mid})",
            }
        )
        if len(options) >= limit:
            break
    return options


def models_grouped_by_tier(
    reg: DynamicRegistry | None = None,
    *,
    query: str = "",
) -> list[tuple[str, list[dict[str, str]]]]:
    """Grouped options for picker UI."""
    reg = reg or DynamicRegistry(ensure_models_yaml())
    groups: list[tuple[str, list[dict[str, str]]]] = []
    for tier in TIER_ORDER:
        items = registry_model_options(reg, limit=50, tier=tier, query=query)
        if items:
            groups.append((TIER_LABELS.get(tier, tier.title()), items))
    other = registry_model_options(reg, limit=50, query=query)
    other_ids = {o["value"] for g in groups for o in g[1]}
    rest = [o for o in other if o["value"] not in other_ids]
    if rest:
        groups.append(("Other", rest))
    return groups


def select_options_for_widget(
    reg: DynamicRegistry | None = None,
    *,
    current_id: str | None = None,
) -> list[tuple[str, str]]:
    """(value, label) tuples for Textual Select — sorted by tier then name."""
    reg = reg or DynamicRegistry(ensure_models_yaml())
    flat: list[tuple[str, str, str]] = []
    for mid in reg.list_models():
        meta = reg.get_model(mid) or {}
        tier = str(meta.get("tier") or "standard")
        name = str(meta.get("display_name") or mid)
        mark = "● " if mid == current_id else ""
        flat.append((tier, mid, f"{mark}{name}"))
    order = {t: i for i, t in enumerate(TIER_ORDER)}
    flat.sort(key=lambda x: (order.get(x[0], 99), x[2].lower()))
    return [(mid, label) for _, mid, label in flat]


def apply_model_choice(ctx: Any, model_id: str) -> str:
    """Persist model and return user-facing confirmation."""
    from src.cli.setup_summary import load_last_setup, save_last_setup, save_project_setup_summary

    reg = ctx.model_registry()
    if model_id not in reg.list_models():
        return f"Unknown model: {model_id}"
    ctx.config.update("default_model", model_id, persist=True)
    meta = reg.get_model(model_id) or {}
    label = meta.get("display_name") or model_id
    tier = meta.get("tier", "")
    g = load_last_setup()
    g["default_model"] = model_id
    save_last_setup(g)
    if ctx.is_initialized():
        save_project_setup_summary(ctx.root, {"default_model": model_id})
    tier_note = f" · {tier}" if tier else ""
    return f"Using {label} ({model_id}){tier_note}"


def prompt_select_model(
    *,
    default_id: str | None = None,
    interactive: bool = True,
) -> str:
    """Numbered picker for CLI setup."""
    reg = DynamicRegistry(ensure_models_yaml())
    options = registry_model_options(reg, limit=40)
    if not options:
        return default_id or "claude-sonnet-4-20250514"
    if not interactive:
        if default_id and default_id in reg.list_models():
            return default_id
        default = reg.get_default_model()
        return str(default["id"]) if default else options[0]["value"]

    default_idx = 1
    if default_id:
        for i, opt in enumerate(options, 1):
            if opt["value"] == default_id:
                default_idx = i
                break

    prompts.console.print("[bold cyan]Select model[/bold cyan] [dim](type number)[/dim]")
    for i, opt in enumerate(options, 1):
        mark = " [green]◀ current[/green]" if opt["value"] == default_id else ""
        prompts.console.print(
            f"  [bold]{i:2}[/bold]  {opt['select_label']}  [dim]{opt['tier']} · {opt['provider']}[/dim]{mark}"
        )
    try:
        from rich.prompt import IntPrompt

        choice = IntPrompt.ask("Number", default=default_idx)
        idx = max(1, min(len(options), choice)) - 1
        return options[idx]["value"]
    except (KeyboardInterrupt, EOFError):
        return default_id or options[0]["value"]


def format_models_table(reg: DynamicRegistry, *, limit: int = 25) -> str:
    lines = ["[bold]Model[/] · [bold]Tier[/] · [bold]Provider[/]"]
    for mid in reg.list_models()[:limit]:
        m = reg.get_model(mid) or {}
        name = m.get("display_name", mid)
        lines.append(f"[cyan]{name}[/] ({mid}) · {m.get('tier', '?')} · {m.get('provider', '?')}")
    rest = len(reg.list_models()) - limit
    if rest > 0:
        lines.append(f"[dim]+{rest} more — use sidebar dropdown[/dim]")
    return "\n".join(lines)
