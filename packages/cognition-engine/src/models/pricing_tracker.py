"""
Model pricing and cost calculation.
"""

from __future__ import annotations

import logging
from typing import Any

from src.models.dynamic_registry import DynamicRegistry

logger = logging.getLogger(__name__)


class PricingTracker:
    """Track pricing and compute session costs."""

    def __init__(self, registry: DynamicRegistry) -> None:
        self.registry = registry
        self._historical: dict[str, dict[str, float]] = {}

    def get_pricing(self, model_id: str) -> dict[str, float]:
        model = self.registry.get_model(model_id)
        if not model:
            return {"input_per_1k": 0.0, "output_per_1k": 0.0, "reasoning_per_1k": 0.0}
        p = model.get("pricing") or {}
        return {
            "input_per_1k": float(p.get("input_per_1k", 0)),
            "output_per_1k": float(p.get("output_per_1k", 0)),
            "reasoning_per_1k": float(p.get("reasoning_per_1k", 0)),
        }

    def calculate_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int = 0,
    ) -> float:
        p = self.get_pricing(model_id)
        cost = (
            input_tokens / 1000 * p["input_per_1k"]
            + output_tokens / 1000 * p["output_per_1k"]
            + reasoning_tokens / 1000 * p["reasoning_per_1k"]
        )
        return round(cost, 6)

    def calculate_session_cost(self, api_calls: list[dict[str, Any]]) -> float:
        total = 0.0
        for call in api_calls:
            total += self.calculate_cost(
                call.get("model_id", ""),
                int(call.get("input_tokens", 0)),
                int(call.get("output_tokens", 0)),
                int(call.get("reasoning_tokens", 0)),
            )
        return round(total, 6)

    def estimate_task_cost(
        self, model_id: str, estimated_input: int, estimated_output: int
    ) -> float:
        return self.calculate_cost(model_id, estimated_input, estimated_output)

    @staticmethod
    def format_cost(cost: float) -> str:
        if cost < 0.01:
            return "$0.00 (less than $0.01)"
        if cost < 1:
            return f"${cost:.3f}"
        return f"${cost:.2f}"

    def compare_costs(
        self, estimated_input: int, estimated_output: int, model_ids: list[str]
    ) -> list[dict[str, Any]]:
        rows = [
            {
                "model_id": mid,
                "cost": self.estimate_task_cost(mid, estimated_input, estimated_output),
            }
            for mid in model_ids
        ]
        rows.sort(key=lambda x: x["cost"])
        if rows:
            base = rows[0]["cost"] or 0.000001
            for r in rows:
                r["pct_diff"] = round((r["cost"] / base - 1) * 100, 1)
        return rows

    def track_price_changes(self) -> list[str]:
        alerts = []
        for mid in self.registry.list_models():
            current = self.get_pricing(mid)
            prev = self._historical.get(mid)
            if prev:
                for key in ("input_per_1k", "output_per_1k"):
                    if prev.get(key) and abs(current[key] - prev[key]) / prev[key] > 0.1:
                        alerts.append(f"{mid}: {key} changed >10%")
            self._historical[mid] = current
        for a in alerts:
            logger.warning("Price change: %s", a)
        return alerts

    def get_cheapest_for_capability(self, capability: str) -> dict[str, Any] | None:
        return self.registry.get_cheapest_model([capability, "chat"])
