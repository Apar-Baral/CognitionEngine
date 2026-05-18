"""Hermes-style quick setup — minimal prompts, env keys, no venv friction."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from src.cli import formatters
from src.cli.context import ProjectContext, resolve_project_root
from src.cli.git_helpers import is_git_repo, write_project_gitignore
from src.cli.setup_summary import save_last_setup, save_project_setup_summary
from src.core.constants import GLOBAL_CONFIG_PATH
from src.models.dynamic_registry import ensure_models_yaml

_ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


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


def _keys_from_env() -> dict[str, str]:
    found: dict[str, str] = {}
    for provider, var in _ENV_KEYS.items():
        val = os.environ.get(var, "").strip()
        if val:
            found[provider] = val
    return found


def needs_api_keys() -> bool:
    data = _load_global()
    keys = {**_keys_from_env(), **(data.get("api_keys") or {})}
    return not any(keys.values())


def hermes_quick_setup(
    project_path: Path | None = None,
    *,
    ask_keys: bool = True,
    init_project: bool = True,
) -> ProjectContext:
    """
    ~3 prompts max: API key, optional goal, done.
    Keys can be set via ANTHROPIC_API_KEY etc. — zero prompts.
    """
    root = resolve_project_root(project_path)
    ensure_models_yaml()

    data = _load_global()
    if not data:
        data = {
            "default_model": "claude-haiku-20240307",
            "shield_sensitivity": "medium",
            "api_keys": {},
            "git": {"auto_commit": False, "auto_commit_message_prefix": "ce:"},
        }

    keys = dict(data.get("api_keys") or {})
    keys.update(_keys_from_env())

    if ask_keys and not any(keys.values()):
        from src.cli import prompts

        formatters.print_rule("Cognition Engine — quick setup")
        formatters.print_info("Tip: export ANTHROPIC_API_KEY=... to skip prompts next time.")
        key = prompts.ask_text("Anthropic API key (recommended)", default="")
        if key.strip():
            keys["anthropic"] = key.strip()
            data["default_model"] = "claude-haiku-20240307"
        else:
            key = prompts.ask_text("OpenAI API key (optional)", default="")
            if key.strip():
                keys["openai"] = key.strip()
                data["default_model"] = "gpt-4o-mini"

    data["api_keys"] = keys
    if not data.get("default_model"):
        if keys.get("anthropic"):
            data["default_model"] = "claude-haiku-20240307"
        elif keys.get("openai"):
            data["default_model"] = "gpt-4o-mini"
        else:
            data["default_model"] = "claude-haiku-20240307"

    _save_global(data)

    ctx = ProjectContext(root)
    if init_project and not ctx.is_initialized():
        ctx.init_project()
        write_project_gitignore(root)
        cfg = root / ".cognition" / "config.yaml"
        if not cfg.is_file():
            cfg.parent.mkdir(parents=True, exist_ok=True)
            cfg.write_text(
                yaml.safe_dump(
                    {
                        "default_model": data["default_model"],
                        "git": {"auto_commit": True, "auto_commit_message_prefix": "ce:"},
                    },
                    default_flow_style=False,
                ),
                encoding="utf-8",
            )
    elif ctx.is_initialized():
        ctx.config.update("default_model", str(data["default_model"]), persist=True)

    summary = {
        "default_model": data["default_model"],
        "project_path": str(root),
        "api_keys_configured": list(keys.keys()),
        "install_type": "slim",
        "git_initialized": is_git_repo(root),
    }
    save_last_setup(summary)
    save_project_setup_summary(root, summary)

    formatters.print_success(f"Ready — project: {root.name} · model: {data['default_model']}")
    if keys:
        formatters.print_info(f"Keys: {', '.join(keys.keys())}")
    else:
        formatters.print_warning("No API keys yet — chat won't work until you add one.")
    formatters.print_info("Start chatting: cognition-engine")
    return ctx
