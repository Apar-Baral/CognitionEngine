"""Hermes-style quick setup — pick model, then API key for that provider."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from src.cli import formatters
from src.cli.api_key_providers import (
    _ENV_KEYS,
    _KEY_LABELS,
    api_key_storage_provider,
    env_var_for_model,
    format_configured_keys,
    has_key_for_model,
    model_provider,
    provider_label_for_model,
)
from src.cli.context import ProjectContext, resolve_project_root
from src.cli.git_helpers import is_git_repo, write_project_gitignore
from src.cli.model_picker import prompt_select_model
from src.cli.setup_summary import save_last_setup, save_project_setup_summary
from src.core.constants import GLOBAL_CONFIG_PATH
from src.models.dynamic_registry import DynamicRegistry, ensure_models_yaml

_PROVIDER_LABELS = {**_KEY_LABELS, "openai_compatible": "OpenAI-compatible (DeepSeek/Kimi)"}


def _safe(text: str | None) -> str:
    return (text or "").strip()


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


def _merged_keys(data: dict[str, Any]) -> dict[str, str]:
    keys = dict(data.get("api_keys") or {})
    keys.update(_keys_from_env())
    return {k: v for k, v in keys.items() if v}


def _provider_for_model(model_id: str) -> str:
    return model_provider(model_id)


def _has_key_for_provider(keys: dict[str, str], provider: str, *, model_id: str = "") -> bool:
    if model_id:
        return has_key_for_model(keys, model_id)
    if keys.get(provider):
        return True
    if provider == "openai_compatible" and (keys.get("openai") or keys.get("deepseek")):
        return True
    if provider == "openrouter" and keys.get("openrouter"):
        return True
    return False


def needs_quick_setup() -> bool:
    """True when model or provider API key is missing."""
    data = _load_global()
    if not data.get("default_model"):
        return True
    keys = _merged_keys(data)
    if not keys:
        return True
    model_id = str(data.get("default_model"))
    if not has_key_for_model(keys, model_id):
        return True
    return False


def needs_api_keys() -> bool:
    return not bool(_merged_keys(_load_global()))


def persist_setup_choices(
    model_id: str,
    *,
    api_key: str | None = None,
    project_root: Path | None = None,
    init_project: bool = True,
) -> dict[str, Any]:
    """Save model + optional API key to global config and init project (no Rich prompts)."""
    from src.cli.model_picker import resolve_model_id

    ensure_models_yaml()
    data = _load_global()
    if not data:
        data = {
            "default_model": "claude-haiku-20240307",
            "shield_sensitivity": "medium",
            "api_keys": {},
            "git": {
                "auto_commit": True,
                "auto_commit_message_prefix": "ce:",
                "user_name": "",
                "user_email": "",
            },
        }

    reg = DynamicRegistry(ensure_models_yaml())
    mid = resolve_model_id(model_id, reg) or model_id.strip()
    bucket = api_key_storage_provider(mid)
    file_keys = dict(data.get("api_keys") or {})
    if api_key and api_key.strip():
        file_keys[bucket] = api_key.strip()
    data["api_keys"] = file_keys
    data["default_model"] = mid
    git = data.setdefault("git", {})
    git.setdefault("auto_commit", True)
    if not git.get("user_name"):
        git["user_name"] = os.environ.get("CE_GIT_USER_NAME", "Apar-Baral")
    if not git.get("user_email"):
        git["user_email"] = os.environ.get("CE_GIT_USER_EMAIL", "dedsecaparb@gmail.com")
    _save_global(data)

    root = (project_root or Path.cwd()).resolve()
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
                        "default_model": mid,
                        "git": {
                            "auto_commit": True,
                            "auto_commit_message_prefix": "ce:",
                            "user_name": git.get("user_name", ""),
                            "user_email": git.get("user_email", ""),
                        },
                    },
                    default_flow_style=False,
                ),
                encoding="utf-8",
            )
    else:
        ctx.config.update("default_model", mid, persist=True)

    summary = {
        "default_model": mid,
        "project_path": str(root),
        "api_keys_configured": list(_merged_keys(data).keys()),
        "api_keys_display": format_configured_keys(
            list(_merged_keys(data).keys()), model_id=mid
        ),
        "install_type": "slim",
        "git_initialized": is_git_repo(root),
    }
    save_last_setup(summary)
    save_project_setup_summary(root, summary)
    return summary


def hermes_quick_setup(
    project_path: Path | None = None,
    *,
    ask_keys: bool = True,
    ask_model: bool = True,
    init_project: bool = True,
) -> ProjectContext:
    """
    1) Choose model (numbered list)
    2) API key for that model's provider (or skip if env/config has it)
    3) Init project
    """
    root = resolve_project_root(project_path)
    ensure_models_yaml()

    data = _load_global()
    if not data:
        data = {
            "default_model": "claude-haiku-20240307",
            "shield_sensitivity": "medium",
            "api_keys": {},
            "git": {
                "auto_commit": True,
                "auto_commit_message_prefix": "ce:",
                "user_name": "",
                "user_email": "",
            },
        }

    keys = _merged_keys(data)

    if ask_model or ask_keys:
        formatters.print_rule("Cognition Engine — setup")
        formatters.print_info("Step 1: choose your model · Step 2: API key for that provider")

    if ask_model:
        default_id = str(data.get("default_model") or "claude-haiku-20240307")
        model_id = prompt_select_model(default_id=default_id, interactive=True)
        data["default_model"] = model_id
    elif not data.get("default_model"):
        data["default_model"] = "claude-haiku-20240307"

    model_id = str(data["default_model"])
    provider = _provider_for_model(model_id)
    reg = DynamicRegistry(ensure_models_yaml())
    meta = reg.get_model(model_id) or {}
    display = meta.get("display_name") or model_id

    if ask_keys and not has_key_for_model(keys, model_id):
        from src.cli import prompts

        bucket = api_key_storage_provider(model_id)
        label = provider_label_for_model(model_id)
        env_var = env_var_for_model(model_id)
        formatters.print_info(f"Step 2: API key for [bold]{display}[/] ({label})")
        formatters.print_info(f"Or export {env_var} and re-run.")
        entered = _safe(
            prompts.ask_text(f"{label} API key", default="")
        )
        if entered:
            keys[bucket] = entered
        else:
            formatters.print_warning("No key entered — chat will not work until /keys or /setup.")

    data["api_keys"] = {**dict(data.get("api_keys") or {}), **keys}
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
                        "default_model": model_id,
                        "git": {
                "auto_commit": True,
                "auto_commit_message_prefix": "ce:",
                "user_name": "",
                "user_email": "",
            },
                    },
                    default_flow_style=False,
                ),
                encoding="utf-8",
            )
    else:
        ctx.config.update("default_model", model_id, persist=True)

    summary = {
        "default_model": model_id,
        "project_path": str(root),
        "api_keys_configured": list(_merged_keys(data).keys()),
        "api_keys_display": format_configured_keys(
            list(_merged_keys(data).keys()), model_id=mid
        ),
        "install_type": "slim",
        "git_initialized": is_git_repo(root),
    }
    save_last_setup(summary)
    save_project_setup_summary(root, summary)

    formatters.print_success(f"Ready — model: {display} ({model_id}) · project: {root.name}")
    active_keys = _merged_keys(data)
    if active_keys:
        formatters.print_info(
            f"API keys: {format_configured_keys(list(active_keys.keys()), model_id=model_id)}"
        )
    formatters.print_info("Launching agent console…")
    return ctx
