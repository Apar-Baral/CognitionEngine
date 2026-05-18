"""
Configuration manager with layered overrides.

Priority (lowest to highest):
  system defaults → ~/.cognition/config.yaml → .cognition/config.yaml
  → environment variables → CLI overrides
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from src.core.constants import (
    COGNITION_DIR,
    DEFAULT_SESSION_BUDGETS,
    GLOBAL_CONFIG_PATH,
    SessionType,
)

# Defaults never include API keys in project files
SYSTEM_DEFAULTS: dict[str, Any] = {
    "default_model": "claude-sonnet",
    "shield_sensitivity": "medium",
    "proxy": {"enabled": False, "port": 8787, "host": "127.0.0.1"},
    "storage": {
        "dna_file": "dna.json",
        "sessions_dir": "sessions",
        "metrics_db": "metrics.db",
        "vector_dir": "chroma",
    },
    "budgets": {st.value: budget for st, budget in DEFAULT_SESSION_BUDGETS.items()},
    "providers": {},
}

ENV_PREFIX = "COGNITION_"
ENV_MAP = {
    "COGNITION_DEFAULT_MODEL": ("default_model",),
    "COGNITION_SHIELD_SENSITIVITY": ("shield_sensitivity",),
    "COGNITION_PROXY_PORT": ("proxy", "port"),
    "COGNITION_PROXY_ENABLED": ("proxy", "enabled"),
}


class Config:
    """Merged configuration with reload support."""

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self._data: dict[str, Any] = {}
        self._cli_overrides: dict[str, Any] = {}
        self._api_keys: dict[str, str] = {}
        self.reload()

    def reload(self) -> None:
        """Reload configuration from all sources."""
        merged: dict[str, Any] = _deep_copy(SYSTEM_DEFAULTS)
        global_path = Path(GLOBAL_CONFIG_PATH).expanduser()
        if global_path.is_file():
            merged = _deep_merge(merged, _load_yaml(global_path))

        project_config = self.project_root / COGNITION_DIR / "config.yaml"
        if project_config.is_file():
            project_data = _load_yaml(project_config)
            # Never merge API keys from project config
            project_data.pop("api_keys", None)
            project_data.pop("providers", None)
            merged = _deep_merge(merged, project_data)

        merged = _deep_merge(merged, _env_overrides())
        merged = _deep_merge(merged, self._cli_overrides)
        self._data = merged
        self._load_api_keys(global_path, project_config)

    def _load_api_keys(self, global_path: Path, project_config: Path) -> None:
        """API keys only from global config and environment — never project files."""
        self._api_keys = {}
        if global_path.is_file():
            raw = _load_yaml(global_path)
            for key, val in (raw.get("api_keys") or {}).items():
                if isinstance(val, str) and val:
                    self._api_keys[key] = val
        for provider in ("anthropic", "openai", "google", "deepseek"):
            env_key = f"{provider.upper()}_API_KEY"
            if os.environ.get(env_key):
                self._api_keys[provider] = os.environ[env_key]

    def get(self, key: str, default: Any = None) -> Any:
        """Get nested key using dot notation, e.g. proxy.port."""
        parts = key.split(".")
        node: Any = self._data
        for part in parts:
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def get_api_key(self, provider: str) -> str | None:
        return self._api_keys.get(provider)

    def get_token_budget(self, session_type: str | SessionType) -> int:
        st = session_type.value if isinstance(session_type, SessionType) else session_type
        budgets = self._data.get("budgets", {})
        if st in budgets:
            return int(budgets[st])
        try:
            return DEFAULT_SESSION_BUDGETS[SessionType(st)]
        except (KeyError, ValueError):
            return DEFAULT_SESSION_BUDGETS[SessionType.BUILD]

    def get_storage_path(self, name: str) -> Path:
        """Resolve storage path relative to .cognition directory."""
        storage = self._data.get("storage", {})
        filename = storage.get(name, name)
        return self.project_root / COGNITION_DIR / filename

    def update(self, key: str, value: Any, *, persist: bool = False) -> None:
        """CLI/runtime override (highest priority). Optionally persist to project config.yaml."""
        if persist:
            self._write_project_config_key(key, value)
        parts = key.split(".")
        node = self._cli_overrides
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        self.reload()

    def _write_project_config_key(self, key: str, value: Any) -> None:
        path = self.project_root / COGNITION_DIR / "config.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = _load_yaml(path) if path.is_file() else {}
        parts = key.split(".")
        node = data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        path.write_text(yaml.safe_dump(data, default_flow_style=False), encoding="utf-8")

    def validate(self) -> list[str]:
        """Validate configuration; return list of error messages."""
        errors: list[str] = []
        sensitivity = self.get("shield_sensitivity", "medium")
        if sensitivity not in ("low", "medium", "high"):
            errors.append(f"Invalid shield_sensitivity: {sensitivity}")

        port = self.get("proxy.port", 8787)
        if not isinstance(port, int) or not (1 <= port <= 65535):
            errors.append(f"Invalid proxy.port: {port}")

        cog = self.project_root / COGNITION_DIR
        try:
            cog.mkdir(parents=True, exist_ok=True)
            if not os.access(cog, os.W_OK):
                errors.append(f"Storage path not writable: {cog}")
        except OSError as e:
            errors.append(f"Cannot access storage path {cog}: {e}")

        return errors

    async def validate_api_keys(self) -> dict[str, bool]:
        """
        Validate API keys with minimal test calls where configured.
        Returns provider -> success mapping.
        """
        import httpx

        results: dict[str, bool] = {}
        for provider, key in self._api_keys.items():
            if not key:
                results[provider] = False
                continue
            try:
                ok = await _minimal_provider_ping(provider, key, httpx.AsyncClient(timeout=5.0))
                results[provider] = ok
            except Exception:
                results[provider] = False
        return results

    def validate_api_keys_sync(self) -> dict[str, bool]:
        """Synchronous wrapper for validate_api_keys."""
        import asyncio

        return asyncio.run(self.validate_api_keys())

    @property
    def data(self) -> dict[str, Any]:
        return _deep_copy(self._data)


async def _minimal_provider_ping(
    provider: str, api_key: str, client: Any
) -> bool:
    """Best-effort minimal reachability check (no token spend where avoidable)."""
    headers: dict[str, str] = {}
    if provider == "anthropic":
        headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
        # HEAD may not be supported; 401 still proves key format reached API
        r = await client.get("https://api.anthropic.com/v1/models", headers=headers)
        return r.status_code in (200, 401, 403)
    if provider == "openai":
        headers = {"Authorization": f"Bearer {api_key}"}
        r = await client.get("https://api.openai.com/v1/models", headers=headers)
        return r.status_code in (200, 401)
    # Unknown provider: key present counts as configured
    return bool(api_key.strip())


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _env_overrides() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for env_name, path in ENV_MAP.items():
        val = os.environ.get(env_name)
        if val is None:
            continue
        node = out
        for part in path[:-1]:
            node = node.setdefault(part, {})
        key = path[-1]
        if key == "port":
            node[key] = int(val)
        elif key == "enabled":
            node[key] = val.lower() in ("1", "true", "yes")
        else:
            node[key] = val
    return out


def _deep_copy(obj: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(obj)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = _deep_copy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


__all__ = ["Config", "SYSTEM_DEFAULTS"]
