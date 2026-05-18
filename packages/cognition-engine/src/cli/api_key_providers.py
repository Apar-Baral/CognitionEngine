"""Map models to API-key storage buckets and env vars (DeepSeek ≠ OpenAI)."""

from __future__ import annotations

from typing import Any

from src.models.dynamic_registry import DynamicRegistry, ensure_models_yaml

_ENV_KEYS = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "openai_compatible": "OPENAI_API_KEY",
}

_KEY_LABELS = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "google": "Google",
    "deepseek": "DeepSeek",
    "openrouter": "OpenRouter",
    "openai_compatible": "OpenAI-compatible",
}


def model_meta(model_id: str) -> dict:
    reg = DynamicRegistry(ensure_models_yaml())
    return reg.get_model(model_id) or {}


def model_provider(model_id: str) -> str:
    return str(model_meta(model_id).get("provider") or "openai")


def api_key_storage_provider(model_id: str) -> str:
    """YAML/env bucket for storing a key (not always equal to HTTP provider)."""
    meta = model_meta(model_id)
    provider = str(meta.get("provider") or "openai")
    if provider != "openai_compatible":
        return provider
    base = str(meta.get("api_base") or "").lower()
    if "deepseek" in base:
        return "deepseek"
    if "moonshot" in base or "kimi" in str(meta.get("display_name") or "").lower():
        return "openai_compatible"
    return "openai_compatible"


def env_var_for_model(model_id: str) -> str:
    bucket = api_key_storage_provider(model_id)
    if bucket == "deepseek":
        return "DEEPSEEK_API_KEY"
    return _ENV_KEYS.get(bucket, "OPENAI_API_KEY")


def provider_label_for_model(model_id: str) -> str:
    bucket = api_key_storage_provider(model_id)
    if bucket == "deepseek":
        return "DeepSeek"
    prov = model_provider(model_id)
    return _KEY_LABELS.get(prov, prov)


def has_key_for_model(keys: dict[str, str], model_id: str) -> bool:
    bucket = api_key_storage_provider(model_id)
    if keys.get(bucket):
        return True
    prov = model_provider(model_id)
    if prov == "openai_compatible":
        return bool(keys.get("deepseek") or keys.get("openai") or keys.get("openai_compatible"))
    if prov == "openrouter":
        return bool(keys.get("openrouter") or keys.get("openai"))
    return bool(keys.get(prov))


def migrate_keys_for_model(keys: dict[str, str], model_id: str) -> dict[str, str]:
    """Move misplaced keys (e.g. DeepSeek key saved under openai) to the right bucket."""
    out = dict(keys)
    bucket = api_key_storage_provider(model_id)
    if bucket == "deepseek":
        if not out.get("deepseek") and out.get("openai"):
            out["deepseek"] = out["openai"]
    return out


def resolve_key_for_model(keys: dict[str, str], model_id: str) -> tuple[str | None, str]:
    """Return (secret, bucket_name) for the active model."""
    migrated = migrate_keys_for_model(keys, model_id)
    bucket = api_key_storage_provider(model_id)
    if migrated.get(bucket):
        return migrated[bucket], bucket
    prov = model_provider(model_id)
    if prov == "openai_compatible":
        for alt in ("deepseek", "openai", "openai_compatible"):
            if migrated.get(alt):
                return migrated[alt], alt
    if prov == "openrouter":
        for alt in ("openrouter", "openai"):
            if migrated.get(alt):
                return migrated[alt], alt
    if migrated.get(prov):
        return migrated[prov], prov
    return None, bucket


def format_active_key_status(config: Any, model_id: str) -> str:
    """One sidebar line: which key the current model uses."""
    from src.cli.model_picker import resolve_model_id
    from src.models.dynamic_registry import DynamicRegistry, ensure_models_yaml

    reg = DynamicRegistry(ensure_models_yaml())
    mid = resolve_model_id(model_id, reg) or model_id
    label = provider_label_for_model(mid)
    env_var = env_var_for_model(mid)
    keys: dict[str, str] = {}
    for bucket in ("anthropic", "openai", "google", "deepseek", "openrouter", "openai_compatible"):
        val = config.get_api_key(bucket)
        if val:
            keys[bucket] = val
    secret, used_bucket = resolve_key_for_model(keys, mid)
    if secret:
        used_label = _KEY_LABELS.get(used_bucket, used_bucket)
        if used_bucket != api_key_storage_provider(mid) and used_bucket != model_provider(mid):
            return (
                f"[dim]Active key[/] [green]{used_label} ✓[/] "
                f"[dim](via {used_label}, needs {label})[/]"
            )
        return f"[dim]Active key[/] [green]{label} ✓[/] [dim]{env_var}[/]"
    return f"[dim]Active key[/] [yellow]{label} missing[/] [dim]· {env_var}[/]"


def format_keys_report(config: Any, model_id: str, *, markup: bool = False) -> str:
    """Model-aware /keys output (plain or Rich markup)."""
    from src.cli.model_picker import resolve_model_id
    from src.models.dynamic_registry import DynamicRegistry, ensure_models_yaml

    reg = DynamicRegistry(ensure_models_yaml())
    mid = resolve_model_id(model_id, reg) or model_id or "?"
    meta = reg.get_model(mid) or {}
    display = meta.get("display_name") or mid
    bucket = api_key_storage_provider(mid)
    label = provider_label_for_model(mid)
    env_var = env_var_for_model(mid)

    keys: dict[str, str] = {}
    for p in ("anthropic", "openai", "google", "deepseek", "openrouter", "openai_compatible"):
        val = config.get_api_key(p)
        if val:
            keys[p] = val
    keys = migrate_keys_for_model(keys, mid)
    secret, used_bucket = resolve_key_for_model(keys, mid)

    def b(s: str) -> str:
        return f"[bold]{s}[/]" if markup else s

    def c(s: str, color: str) -> str:
        return f"[{color}]{s}[/]" if markup else s

    lines = [
        f"{b('Model')} {display} ({mid})",
        f"{b('Uses')} {label} · bucket {bucket} · env {env_var}",
        "",
    ]
    if secret:
        lines.append(
            f"{c('✓ Active key ready', 'green')} ({_KEY_LABELS.get(used_bucket, used_bucket)})"
        )
    else:
        lines.append(f"{c('✗ No key for this model', 'yellow')} — Setup keys or export {env_var}")

    lines.append("")
    lines.append("All stored keys:" if not markup else "[dim]All stored keys:[/]")
    for p in ("anthropic", "deepseek", "openai", "google", "openrouter"):
        mark = "✓" if keys.get(p) else "·"
        name = _KEY_LABELS.get(p, p)
        note = ""
        if p == bucket:
            note = " ← active bucket"
        elif p == "openai" and bucket == "deepseek" and keys.get("openai") and not keys.get("deepseek"):
            note = " (legacy — re-save in Setup keys)"
        lines.append(f"  {mark} {name}{note}")
    return "\n".join(lines)


def format_configured_keys(keys: list[str], *, model_id: str | None = None) -> str:
    """Human-readable key list for sidebar (avoid showing 'openai' for DeepSeek-only)."""
    if not keys:
        return ""
    labels: list[str] = []
    seen: set[str] = set()
    for k in keys:
        label = _KEY_LABELS.get(k, k)
        if model_id and k == "openai" and api_key_storage_provider(model_id) == "deepseek":
            if "deepseek" in keys:
                continue
            label = "OpenAI (legacy slot)"
        if label not in seen:
            seen.add(label)
            labels.append(label)
    return ", ".join(labels)
