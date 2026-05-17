"""
Circuit breaker, rate limits, and model fallback resilience.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.models.dynamic_registry import DynamicRegistry

logger = logging.getLogger(__name__)


@dataclass
class _CircuitState:
    failures: int = 0
    last_failure: float = 0.0
    open_until: float = 0.0
    cooldown_seconds: float = 300.0
    state: str = "closed"  # closed | open | half_open


class FallbackManager:
    """Track model health and provide fallbacks."""

    def __init__(
        self,
        registry: DynamicRegistry,
        *,
        failure_threshold: int = 3,
        failure_window_seconds: float = 60.0,
        initial_cooldown: float = 300.0,
    ) -> None:
        self.registry = registry
        self.failure_threshold = failure_threshold
        self.failure_window = failure_window_seconds
        self.initial_cooldown = initial_cooldown
        self._circuits: dict[str, _CircuitState] = {}
        self._rate_limits: dict[str, float] = {}
        self._stats: dict[str, dict[str, Any]] = {}

    def is_model_available(self, model_id: str) -> bool:
        now = time.monotonic()
        if model_id in self._rate_limits and now < self._rate_limits[model_id]:
            return False
        circ = self._circuits.get(model_id)
        if not circ:
            return True
        if circ.state == "closed":
            return True
        if circ.state == "open":
            if now >= circ.open_until:
                circ.state = "half_open"
                return True
            return False
        return True  # half_open allows probe

    def record_success(self, model_id: str) -> None:
        circ = self._circuits.setdefault(model_id, _CircuitState(cooldown_seconds=self.initial_cooldown))
        circ.failures = 0
        circ.state = "closed"
        circ.cooldown_seconds = self.initial_cooldown
        st = self._stats.setdefault(model_id, {"success": 0, "failure": 0, "latencies": []})
        st["success"] = st.get("success", 0) + 1

    def record_failure(self, model_id: str, error: Any = None) -> None:
        _ = error
        now = time.monotonic()
        circ = self._circuits.setdefault(model_id, _CircuitState(cooldown_seconds=self.initial_cooldown))
        if now - circ.last_failure > self.failure_window:
            circ.failures = 0
        circ.failures += 1
        circ.last_failure = now
        st = self._stats.setdefault(model_id, {"success": 0, "failure": 0})
        st["failure"] = st.get("failure", 0) + 1
        if circ.failures >= self.failure_threshold:
            circ.state = "open"
            circ.open_until = now + circ.cooldown_seconds
            circ.cooldown_seconds = min(circ.cooldown_seconds * 2, 3600.0)
            logger.warning("Circuit open for %s until %.0fs cooldown", model_id, circ.cooldown_seconds)

    def get_available_models(self) -> list[str]:
        return [mid for mid in self.registry.list_models() if self.is_model_available(mid)]

    def get_fallback(self, model_id: str) -> str:
        if self.is_model_available(model_id):
            return model_id
        model = self.registry.get_model(model_id)
        tier = model.get("tier", "standard") if model else "standard"
        caps = (model or {}).get("capabilities") or ["chat"]
        for t in ("economy", "standard", "premium"):
            for m in self.registry.list_by_tier(t):
                if m["id"] != model_id and self.is_model_available(m["id"]):
                    if all(c in (m.get("capabilities") or []) for c in caps):
                        return m["id"]
        for mid in self.registry.list_models():
            if mid != model_id and self.is_model_available(mid):
                return mid
        raise RuntimeError(f"No fallback available for {model_id}")

    def record_rate_limit(self, model_id: str, retry_after_seconds: float) -> None:
        self._rate_limits[model_id] = time.monotonic() + retry_after_seconds

    def health_check(self, api_keys: dict[str, str] | None = None) -> dict[str, bool]:
        """Mark models available/unavailable (ping is optional; registry-only by default)."""
        results = {}
        for mid in self.registry.list_models():
            results[mid] = self.is_model_available(mid)
        _ = api_keys
        return results

    def get_reliability_stats(self) -> dict[str, dict[str, Any]]:
        out = {}
        for mid, st in self._stats.items():
            total = st.get("success", 0) + st.get("failure", 0)
            out[mid] = {
                "error_rate": st.get("failure", 0) / total if total else 0,
                "success_count": st.get("success", 0),
                "failure_count": st.get("failure", 0),
            }
        return out

    def get_status(self) -> dict[str, str]:
        status = {}
        now = time.monotonic()
        for mid in self.registry.list_models():
            if mid in self._rate_limits and now < self._rate_limits[mid]:
                status[mid] = "rate-limited"
            elif mid in self._circuits and self._circuits[mid].state == "open":
                status[mid] = "circuit-open"
            elif mid in self._circuits and self._circuits[mid].state == "half_open":
                status[mid] = "probing"
            elif self.is_model_available(mid):
                status[mid] = "available"
            else:
                status[mid] = "unavailable"
        return status

    def force_close_circuit(self, model_id: str) -> None:
        """Test helper: reset circuit."""
        if model_id in self._circuits:
            self._circuits[model_id].state = "closed"
            self._circuits[model_id].failures = 0

    def force_open_probe_ready(self, model_id: str) -> None:
        """Test helper: set half-open."""
        circ = self._circuits.setdefault(model_id, _CircuitState())
        circ.state = "half_open"
        circ.open_until = 0
