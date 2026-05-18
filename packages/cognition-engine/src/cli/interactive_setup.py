"""In-terminal first-run setup (keys, model) — no separate wizard required."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.cli import formatters, prompts
from src.cli.context import ProjectContext, resolve_project_root
from src.cli.model_picker import prompt_select_model
from src.core.constants import GLOBAL_CONFIG_PATH
from src.cli.setup_wizard import global_config_template, setup_global


def _load_global() -> dict[str, Any]:
    path = Path(GLOBAL_CONFIG_PATH).expanduser()
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _save_global(data: dict[str, Any]) -> None:
    path = Path(GLOBAL_CONFIG_PATH).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, default_flow_style=False), encoding="utf-8")


def provider_for_model(model_id: str, ctx: ProjectContext) -> str:
    reg = ctx.model_registry()
    meta = reg.get_model(model_id) or {}
    return str(meta.get("provider") or "openai")


def has_api_key_for_model(model_id: str, ctx: ProjectContext) -> bool:
    from src.agent.orchestrator import AgentOrchestrator

    meta = ctx.model_registry().get_model(model_id) or {}
    provider = str(meta.get("provider") or "openai")
    return AgentOrchestrator.resolve_api_key(ctx.config, provider) is not None


def ensure_interactive_ready(
    project_root: Path | None = None,
    *,
    interactive: bool = True,
) -> ProjectContext:
    """
    Run minimal setup in the terminal if global config or API keys are missing.
    Returns project context for the resolved root.
    """
    root = resolve_project_root(project_root)
    ctx = ProjectContext(root)
    global_path = Path(GLOBAL_CONFIG_PATH).expanduser()

    if not global_path.is_file():
        formatters.print_rule("First-time Cognition Engine setup")
        setup_global(interactive=interactive)
    else:
        data = _load_global()
        keys = data.get("api_keys") or {}
        model_id = str(ctx.config.get("default_model", ""))
        provider = provider_for_model(model_id, ctx)
        if interactive and not keys:
            formatters.print_warning("No API keys in ~/.cognition/config.yaml")
            if prompts.confirm("Configure API keys now?", default=True):
                for pname in ("anthropic", "openai", "deepseek", "google"):
                    key = prompts.ask_text(f"{pname} API key (empty to skip)", default="")
                    if key.strip():
                        data.setdefault("api_keys", {})[pname] = key.strip()
                _save_global(data)
                ctx.config.reload()
        elif interactive and not has_api_key_for_model(model_id, ctx):
            formatters.print_warning(
                f"No API key for model '{model_id}' (provider: {provider})."
            )
            if prompts.confirm(f"Add {provider} API key now?", default=True):
                key = prompts.ask_text(f"{provider} API key", default="")
                if key.strip():
                    data.setdefault("api_keys", {})[provider] = key.strip()
                    if provider == "openai_compatible":
                        data["api_keys"].setdefault("openai", key.strip())
                    _save_global(data)
                    ctx.config.reload()

    # Keep project model aligned with global default after setup
    g = _load_global()
    g_model = g.get("default_model")
    if g_model and ctx.is_initialized():
        ctx.config.update("default_model", str(g_model), persist=True)

    return ctx


def run_quick_setup_in_terminal(project_root: Path | None = None) -> None:
    """Full interactive setup from the REPL (/setup) or first launch."""
    from src.cli.setup_wizard import run_full_setup

    root = resolve_project_root(project_root)
    formatters.print_rule("Cognition Engine setup")
    run_full_setup(root, interactive=True)
