"""
Intelligent model routing by task complexity, budget zone, and capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.core.constants import BudgetZone, SessionType
from src.models.dynamic_registry import DynamicRegistry
from src.models.fallback_manager import FallbackManager
from src.models.pricing_tracker import PricingTracker

TIER_ORDER = ["economy", "standard", "premium"]
COMPLEXITY_TO_TIER = {"LOW": "economy", "MEDIUM": "standard", "HIGH": "premium"}


@dataclass
class RouteResult:
    model_id: str
    model_display_name: str
    tier: str
    estimated_cost: float
    explanation: str


class IntelligentRouter:
    """Select optimal model for each task."""

    def __init__(
        self,
        registry: DynamicRegistry,
        config: dict[str, Any] | None = None,
        *,
        fallback: FallbackManager | None = None,
    ) -> None:
        self.registry = registry
        self.config = config or {}
        self.fallback = fallback or FallbackManager(registry)
        self.pricing = PricingTracker(registry)
        self._stats: dict[str, int] = {"premium": 0, "standard": 0, "economy": 0}

    def route_task(
        self,
        *,
        task_complexity: str = "MEDIUM",
        task_type: str = SessionType.BUILD.value,
        required_capabilities: list[str] | None = None,
        budget_zone: str = BudgetZone.GREEN.value,
        preferred_model: str | None = None,
        estimated_tokens: int | None = None,
    ) -> RouteResult:
        caps = required_capabilities or ["chat"]
        est_in = estimated_tokens or 8000
        est_out = max(500, est_in // 10)

        if preferred_model:
            model = self.registry.get_model(preferred_model)
            if model and all(c in (model.get("capabilities") or []) for c in caps):
                if self.fallback.is_model_available(preferred_model):
                    cost = self.pricing.estimate_task_cost(preferred_model, est_in, est_out)
                    return RouteResult(
                        preferred_model,
                        model.get("display_name", preferred_model),
                        model.get("tier", "standard"),
                        cost,
                        f"Using user-preferred model {preferred_model}.",
                    )

        eligible = [
            m
            for m in self.registry._models.values()
            if all(c in (m.get("capabilities") or []) for c in caps)
            and self.fallback.is_model_available(m["id"])
        ]
        if not eligible:
            raise RuntimeError("No capable models available for routing")

        target_tier = COMPLEXITY_TO_TIER.get(task_complexity.upper(), "standard")
        target_tier = self._adjust_tier_for_budget(target_tier, task_complexity, budget_zone)

        tier_models = [m for m in eligible if m.get("tier") == target_tier]
        if not tier_models:
            tier_models = self._escalate_tier(eligible, target_tier)
        if not tier_models:
            tier_models = eligible

        if task_complexity.upper() == "HIGH" and "extended_thinking" in caps:
            thinking = [m for m in tier_models if "extended_thinking" in (m.get("capabilities") or [])]
            if thinking:
                tier_models = thinking

        chosen = self._pick_cheapest_reliable(tier_models)
        cost = self.pricing.estimate_task_cost(chosen["id"], est_in, est_out)
        self._stats[chosen.get("tier", "standard")] = self._stats.get(chosen.get("tier", "standard"), 0) + 1

        result = RouteResult(
            chosen["id"],
            chosen.get("display_name", chosen["id"]),
            chosen.get("tier", "standard"),
            cost,
            self._build_explanation(chosen, task_complexity, budget_zone, cost, task_type),
        )
        return result

    def explain_routing(self, result: RouteResult) -> str:
        return (
            f"Selected {result.model_display_name} ({result.tier} tier): "
            f"{result.explanation} Estimated cost: ${result.estimated_cost:.4f}."
        )

    def get_fallback_chain(self, model_id: str) -> list[str]:
        model = self.registry.get_model(model_id)
        if not model:
            return []
        tier = model.get("tier", "standard")
        idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else 1
        chain = [model_id]
        caps = model.get("capabilities") or ["chat"]
        for t in TIER_ORDER[idx + 1 :]:
            for m in self.registry.list_by_tier(t):
                if m["id"] != model_id and all(c in (m.get("capabilities") or []) for c in caps):
                    chain.append(m["id"])
        for m in self.registry._models.values():
            if m["id"] not in chain and m.get("provider") != model.get("provider"):
                if all(c in (m.get("capabilities") or []) for c in caps):
                    chain.append(m["id"])
        return chain

    def compare_costs(
        self, estimated_input: int, estimated_output: int, capabilities: list[str] | None = None
    ) -> list[dict[str, Any]]:
        caps = capabilities or ["chat"]
        rows = []
        for mid in self.registry.list_models():
            m = self.registry.get_model(mid)
            if not m or not all(c in (m.get("capabilities") or []) for c in caps):
                continue
            cost = self.pricing.estimate_task_cost(mid, estimated_input, estimated_output)
            rows.append({"model_id": mid, "display_name": m.get("display_name"), "cost": cost})
        rows.sort(key=lambda x: x["cost"])
        if rows:
            cheapest = rows[0]["cost"] or 0.000001
            for r in rows:
                r["pct_vs_cheapest"] = round((r["cost"] / cheapest - 1) * 100, 1)
        return rows

    def get_routing_stats(self) -> dict[str, Any]:
        return dict(self._stats)

    def _adjust_tier_for_budget(
        self, tier: str, complexity: str, zone: str
    ) -> str:
        z = zone.lower()
        idx = TIER_ORDER.index(tier) if tier in TIER_ORDER else 1
        if z in (BudgetZone.RED.value, BudgetZone.WRAP_UP.value):
            return "economy"
        if z == BudgetZone.YELLOW.value and complexity.upper() == "MEDIUM":
            return TIER_ORDER[max(0, idx - 1)]
        return tier

    def _escalate_tier(self, eligible: list[dict], target: str) -> list[dict]:
        if target in TIER_ORDER:
            idx = TIER_ORDER.index(target)
            for t in TIER_ORDER[idx - 1 :: -1] + TIER_ORDER[idx + 1 :]:
                found = [m for m in eligible if m.get("tier") == t]
                if found:
                    return found
        return eligible

    def _pick_cheapest_reliable(self, models: list[dict[str, Any]]) -> dict[str, Any]:
        def key(m: dict[str, Any]) -> tuple[float, float]:
            p = m.get("pricing") or {}
            cost = float(p.get("input_per_1k", 0)) + float(p.get("output_per_1k", 0))
            rel = self.fallback.get_reliability_stats().get(m["id"], {}).get("error_rate", 0)
            return (cost, rel)

        return min(models, key=key)

    def _build_explanation(
        self, model: dict, complexity: str, zone: str, cost: float, task_type: str
    ) -> str:
        return (
            f"task is {complexity} complexity ({task_type}), budget zone {zone}; "
            f"matched {model.get('tier')} tier at ${cost:.4f} estimated."
        )
