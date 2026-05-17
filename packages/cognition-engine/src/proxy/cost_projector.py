"""
Real-time cost calculation from token usage and model pricing.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLDS = {
    "info": 1.0,
    "warning": 5.0,
    "critical": 10.0,
}


class CostProjector:
    """Translate tokens into dollar costs with alerts and projections."""

    def __init__(
        self,
        pricing: dict[str, dict[str, float]],
        *,
        cost_thresholds: dict[str, float] | None = None,
    ) -> None:
        self.pricing = pricing
        self.cost_thresholds = cost_thresholds or dict(DEFAULT_THRESHOLDS)
        self._session_calls: list[dict[str, Any]] = []
        self._alerts_fired: list[str] = []

    def calculate_cost(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int = 0,
    ) -> float:
        prices = self._prices_for(model_id)
        cost = (
            (input_tokens / 1000.0) * prices["input"]
            + (output_tokens / 1000.0) * prices["output"]
            + (reasoning_tokens / 1000.0) * prices.get("reasoning", 0.0)
        )
        return round(cost, 4)

    def record_call(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
        reasoning_tokens: int = 0,
    ) -> float:
        cost = self.calculate_cost(model_id, input_tokens, output_tokens, reasoning_tokens)
        self._session_calls.append(
            {
                "model_id": model_id,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "reasoning_tokens": reasoning_tokens,
                "cost": cost,
            }
        )
        self.cost_alerts(self.get_session_cost())
        return cost

    def get_session_cost(self) -> float:
        return round(sum(c["cost"] for c in self._session_calls), 4)

    def project_remaining_cost(self, remaining_tokens: int) -> float:
        total_tokens = sum(
            c["input_tokens"] + c["output_tokens"] + c.get("reasoning_tokens", 0)
            for c in self._session_calls
        )
        total_cost = self.get_session_cost()
        if total_tokens <= 0:
            return 0.0
        per_token = total_cost / total_tokens
        return round(remaining_tokens * per_token, 4)

    @staticmethod
    def format_cost(cost: float) -> str:
        if cost < 0.01:
            return f"${cost:.4f}"
        if cost < 1:
            return f"${cost:.2f}"
        return f"${cost:.2f}"

    def get_cost_breakdown(self) -> dict[str, Any]:
        by_model: dict[str, float] = {}
        input_total = 0
        output_total = 0
        for call in self._session_calls:
            mid = call["model_id"]
            by_model[mid] = by_model.get(mid, 0.0) + call["cost"]
            input_total += call["input_tokens"]
            output_total += call["output_tokens"]
        return {
            "total": self.get_session_cost(),
            "by_model": by_model,
            "input_tokens": input_total,
            "output_tokens": output_total,
            "call_count": len(self._session_calls),
        }

    def project_session_cost(
        self,
        predicted_tokens: int,
        model_id: str,
        *,
        output_ratio: float = 0.25,
    ) -> float:
        input_tokens = int(predicted_tokens * (1.0 - output_ratio))
        output_tokens = predicted_tokens - input_tokens
        return self.calculate_cost(model_id, input_tokens, output_tokens)

    def get_cost_savings(self) -> dict[str, Any]:
        actual = self.get_session_cost()
        if not self._session_calls:
            return {"savings": 0.0, "percentage": 0.0}
        expensive = max(self.pricing.values(), key=lambda p: p["input"] + p["output"])
        max_cost = 0.0
        for call in self._session_calls:
            max_cost += (
                (call["input_tokens"] / 1000.0) * expensive["input"]
                + (call["output_tokens"] / 1000.0) * expensive["output"]
            )
        savings = max(0.0, max_cost - actual)
        pct = round(100.0 * savings / max_cost, 2) if max_cost else 0.0
        return {"savings": round(savings, 4), "percentage": pct, "hypothetical_max": round(max_cost, 4)}

    def cost_alerts(self, session_cost: float) -> list[dict[str, str]]:
        alerts: list[dict[str, str]] = []
        for level, threshold in sorted(
            self.cost_thresholds.items(), key=lambda x: x[1]
        ):
            key = f"{level}:{threshold}"
            if session_cost >= threshold and key not in self._alerts_fired:
                self._alerts_fired.append(key)
                msg = f"Session cost {self.format_cost(session_cost)} exceeded {level} threshold {self.format_cost(threshold)}"
                alerts.append({"level": level, "message": msg})
                logger.info(msg)
        return alerts

    def _prices_for(self, model_id: str) -> dict[str, float]:
        if model_id in self.pricing:
            return self.pricing[model_id]
        for key, val in self.pricing.items():
            if key in model_id:
                return val
        return {"input": 3.0, "output": 15.0, "reasoning": 0.0}
