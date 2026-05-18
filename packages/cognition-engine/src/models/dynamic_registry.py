"""
Dynamic model registry — loads ~/.cognition/models.yaml with hot reload.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

from src.core.constants import MODELS_REGISTRY_PATH

logger = logging.getLogger(__name__)

KNOWN_CAPABILITIES = frozenset(
    {"chat", "tool_use", "vision", "extended_thinking", "streaming", "json_mode"}
)
KNOWN_TIERS = frozenset({"premium", "standard", "economy"})
KNOWN_PROVIDERS = frozenset(
    {"anthropic", "openai", "openai_compatible", "deepseek", "google", "openrouter", "ollama", "custom"}
)
# Registry id → upstream API model name (when they differ).
_API_MODEL_DEFAULTS: dict[str, str] = {
    "deepseek-r4-pro": "deepseek-v4-pro",
}

REQUIRED_FIELDS = (
    "id",
    "provider",
    "display_name",
    "api_base",
    "endpoint",
    "auth_header",
    "auth_prefix",
    "capabilities",
    "max_context",
    "max_output",
    "pricing",
    "tokenizer",
    "default",
    "tier",
)


def bundled_models_path() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "config" / "default_models.yaml"
        if candidate.is_file():
            return candidate
    return Path(__file__).resolve().parents[2] / "config" / "default_models.yaml"


def ensure_models_yaml(path: Path | None = None) -> Path:
    """Create ~/.cognition/models.yaml from bundled defaults if missing."""
    target = Path(path or MODELS_REGISTRY_PATH).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file():
        src = bundled_models_path()
        if src.is_file():
            shutil.copy(src, target)
            logger.info("Installed default models registry at %s", target)
        else:
            target.write_text("models: []\n", encoding="utf-8")
    return target


class DynamicRegistry:
    """In-memory model registry backed by YAML."""

    def __init__(self, config_path: str | Path | None = None, *, watch: bool = False) -> None:
        self.config_path = ensure_models_yaml(
            Path(config_path) if config_path else None
        )
        self._models: dict[str, dict[str, Any]] = {}
        self._mtime: float = 0.0
        self._watch_stop = threading.Event()
        self._watch_thread: threading.Thread | None = None
        self.load()
        if watch:
            self.start_file_watcher()

    def load(self) -> int:
        """Load and validate models from YAML."""
        if not self.config_path.is_file():
            self._models = {}
            return 0
        self._mtime = self.config_path.stat().st_mtime
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        items = raw.get("models") or []
        loaded: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            errors = self.validate_model(item)
            if errors:
                logger.warning("Skipping model %s: %s", item.get("id"), "; ".join(errors))
                continue
            mid = str(item["id"])
            model = dict(item)
            loaded[mid] = model
        for mid, api_name in _API_MODEL_DEFAULTS.items():
            if mid in loaded and not loaded[mid].get("api_model"):
                loaded[mid]["api_model"] = api_name
        self._models = loaded
        logger.info("Loaded %d models from %s", len(loaded), self.config_path)
        return len(loaded)

    def reload(self) -> dict[str, list[str]]:
        """Reload file and report added/removed/modified IDs."""
        old = set(self._models)
        previous = {k: dict(v) for k, v in self._models.items()}
        self.load()
        new = set(self._models)
        added = sorted(new - old)
        removed = sorted(old - new)
        modified = sorted(
            mid
            for mid in new & old
            if previous[mid] != self._models[mid]
        )
        return {"added": added, "removed": removed, "modified": modified}

    def list_models(self) -> list[str]:
        return sorted(self._models)

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        m = self._models.get(model_id)
        return dict(m) if m else None

    @staticmethod
    def api_model_name(model: dict[str, Any]) -> str:
        """Name sent to the provider API (may differ from registry id)."""
        return str(model.get("api_model") or model.get("id") or "")

    def list_by_provider(self, provider: str) -> list[dict[str, Any]]:
        return [dict(m) for m in self._models.values() if m.get("provider") == provider]

    def list_by_capability(self, capability: str) -> list[dict[str, Any]]:
        return [
            dict(m)
            for m in self._models.values()
            if capability in (m.get("capabilities") or [])
        ]

    def list_by_tier(self, tier: str) -> list[dict[str, Any]]:
        return [dict(m) for m in self._models.values() if m.get("tier") == tier]

    def get_default_model(self, tier: str | None = None) -> dict[str, Any] | None:
        candidates = list(self._models.values())
        if tier:
            candidates = [m for m in candidates if m.get("tier") == tier]
        for m in candidates:
            if m.get("default"):
                return dict(m)
        return dict(candidates[0]) if candidates else None

    def get_cheapest_model(
        self, required_capabilities: list[str] | None = None
    ) -> dict[str, Any] | None:
        caps = required_capabilities or ["chat"]
        eligible = [
            m
            for m in self._models.values()
            if all(c in (m.get("capabilities") or []) for c in caps)
        ]
        if not eligible:
            return None

        def cost(m: dict[str, Any]) -> float:
            p = m.get("pricing") or {}
            return float(p.get("input_per_1k", 0)) + float(p.get("output_per_1k", 0))

        return dict(min(eligible, key=cost))

    def add_custom_model(self, model: dict[str, Any]) -> str:
        errors = self.validate_model(model)
        if errors:
            raise ValueError("; ".join(errors))
        model = dict(model)
        model["custom"] = True
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        models = raw.setdefault("models", [])
        models.append(model)
        self.config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        self.load()
        return str(model["id"])

    def remove_custom_model(self, model_id: str) -> bool:
        m = self._models.get(model_id)
        if not m or not m.get("custom"):
            return False
        raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
        raw["models"] = [x for x in raw.get("models", []) if x.get("id") != model_id]
        self.config_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        self.load()
        return True

    def validate_model(self, model: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for field in REQUIRED_FIELDS:
            if field not in model:
                errors.append(f"missing field: {field}")
        if model.get("tier") and model["tier"] not in KNOWN_TIERS:
            errors.append(f"invalid tier: {model['tier']}")
        for cap in model.get("capabilities") or []:
            if cap not in KNOWN_CAPABILITIES:
                errors.append(f"unknown capability: {cap}")
        try:
            parsed = urlparse(str(model.get("api_base", "")))
            if parsed.scheme not in ("http", "https"):
                errors.append("api_base must be http(s) URL")
        except Exception:
            errors.append("invalid api_base URL")
        pricing = model.get("pricing")
        if not isinstance(pricing, dict):
            errors.append("pricing must be a dict")
        else:
            for key in ("input_per_1k", "output_per_1k"):
                if key not in pricing:
                    errors.append(f"pricing missing {key}")
        return errors

    def start_file_watcher(self, interval: float = 2.0) -> None:
        if self._watch_thread and self._watch_thread.is_alive():
            return
        self._watch_stop.clear()

        def _loop() -> None:
            while not self._watch_stop.wait(interval):
                try:
                    if self.config_path.is_file():
                        mtime = self.config_path.stat().st_mtime
                        if mtime > self._mtime:
                            changes = self.reload()
                            if any(changes.values()):
                                logger.info("models.yaml reloaded: %s", changes)
                except OSError:
                    pass

        self._watch_thread = threading.Thread(target=_loop, daemon=True, name="models-watcher")
        self._watch_thread.start()

    def stop_file_watcher(self) -> None:
        self._watch_stop.set()
