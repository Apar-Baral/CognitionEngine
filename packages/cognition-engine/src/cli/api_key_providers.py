"""Map models to API-key storage buckets and env vars (DeepSeek ≠ OpenAI)."""

from __future__ import annotations

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
