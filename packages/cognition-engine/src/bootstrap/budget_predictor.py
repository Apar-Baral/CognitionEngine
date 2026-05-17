"""
Token budget prediction from historical session metrics.
"""

from __future__ import annotations

import json
import math
from typing import Any, Literal

from src.core.constants import DEFAULT_SESSION_BUDGETS, SessionType
from src.core.types import ModelConfig
from src.dna.query import DNAQuery
from src.memory.metrics_store import MetricsStore

TaskComplexity = Literal["LOW", "MEDIUM", "HIGH"]

COMPLEXITY_SCALE: dict[TaskComplexity, float] = {
    "LOW": 0.7,
    "MEDIUM": 1.0,
    "HIGH": 1.35,
}

DEFAULT_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet": (3.0, 15.0),
    "claude-opus": (15.0, 75.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "deepseek-chat": (0.14, 0.28),
}


class BudgetPredictor:
    """Predict session token usage from metrics history."""

    def __init__(self, metrics: MetricsStore, query: DNAQuery) -> None:
        self.metrics = metrics
        self.query = query

    def predict(
        self,
        session_type: str | SessionType,
        phase_id: str,
        files_affected: int,
        complexity: TaskComplexity = "MEDIUM",
    ) -> dict[str, Any]:
        st = session_type.value if isinstance(session_type, SessionType) else session_type
        exact = self._sessions_matching(session_type=st, phase_id=phase_id)

        if len(exact) >= 3:
            values = [float(v) for v in exact]
            mean = sum(values) / len(values)
            if len(values) > 1:
                variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
                std = math.sqrt(variance)
            else:
                std = mean * 0.15
            return {
                "estimated_tokens": int(round(mean)),
                "confidence_interval": {
                    "low": int(max(0, mean - 1.5 * std)),
                    "high": int(mean + 1.5 * std),
                },
                "confidence_level": min(95, 60 + len(exact) * 5),
                "basis": f"exact_match:{len(exact)} sessions type={st} phase={phase_id}",
            }

        similar = self._sessions_matching(session_type=st, phase_id=None, complexity=complexity)
        if similar:
            values = [float(v) for v in similar]
            mean = sum(values) / len(values)
            file_factor = 1.0 + max(0, files_affected - 3) * 0.08
            scaled = mean * COMPLEXITY_SCALE.get(complexity, 1.0) * file_factor
            spread = scaled * 0.35
            return {
                "estimated_tokens": int(round(scaled)),
                "confidence_interval": {
                    "low": int(max(0, scaled - spread)),
                    "high": int(scaled + spread),
                },
                "confidence_level": 55,
                "basis": (
                    f"similar_match:{len(similar)} sessions type={st} "
                    f"complexity={complexity} files_scale={file_factor:.2f}"
                ),
            }

        try:
            default = DEFAULT_SESSION_BUDGETS[SessionType(st)]
        except (KeyError, ValueError):
            default = DEFAULT_SESSION_BUDGETS[SessionType.BUILD]

        scaled = int(default * COMPLEXITY_SCALE.get(complexity, 1.0))
        return {
            "estimated_tokens": scaled,
            "confidence_interval": {"low": int(scaled * 0.5), "high": int(scaled * 1.8)},
            "confidence_level": 30,
            "basis": f"global_default:{st} (no historical sessions)",
        }

    def calibrate(
        self,
        session_type: str | SessionType,
        phase_id: str,
        actual_tokens: int,
        *,
        complexity: TaskComplexity = "MEDIUM",
        files_affected: int = 0,
        session_id: int | None = None,
    ) -> None:
        """Store actual consumption for future predictions."""
        st = session_type.value if isinstance(session_type, SessionType) else session_type
        self.metrics.record_metric(
            "tokens_per_session",
            float(actual_tokens),
            tags={
                "session_type": st,
                "phase_id": phase_id,
                "complexity": complexity,
                "files_affected": files_affected,
            },
            session_id=session_id,
        )
        predicted = self.predict(st, phase_id, files_affected, complexity)
        est = predicted["estimated_tokens"]
        if est > 0:
            error_pct = abs(actual_tokens - est) / est * 100.0
            self.metrics.record_metric(
                "prediction_error_pct",
                error_pct,
                tags={"session_type": st, "phase_id": phase_id},
                session_id=session_id,
            )

    def get_recommended_budget(self, predicted_tokens: int | dict[str, Any]) -> int:
        if isinstance(predicted_tokens, dict):
            predicted_tokens = int(predicted_tokens.get("estimated_tokens", 0))
        buffer_pct = self._buffer_percentage()
        return int(predicted_tokens * (1.0 + buffer_pct / 100.0))

    def get_cost_estimate(
        self,
        predicted_tokens: int | dict[str, Any],
        model_id: str,
        *,
        output_ratio: float = 0.25,
    ) -> float:
        if isinstance(predicted_tokens, dict):
            predicted_tokens = int(predicted_tokens.get("estimated_tokens", 0))
        input_price, output_price = DEFAULT_MODEL_PRICING.get(
            model_id,
            (3.0, 15.0),
        )
        input_tokens = predicted_tokens * (1.0 - output_ratio)
        output_tokens = predicted_tokens * output_ratio
        cost = (input_tokens / 1000.0) * input_price + (output_tokens / 1000.0) * output_price
        return round(cost, 4)

    def get_cost_estimate_from_config(
        self,
        predicted_tokens: int,
        model: ModelConfig,
        *,
        output_ratio: float = 0.25,
    ) -> float:
        input_tokens = predicted_tokens * (1.0 - output_ratio)
        output_tokens = predicted_tokens * output_ratio
        cost = (input_tokens / 1000.0) * model.input_price_per_1k + (
            output_tokens / 1000.0
        ) * model.output_price_per_1k
        return round(cost, 4)

    def _buffer_percentage(self) -> float:
        errors = self._recent_prediction_errors(limit=10)
        if len(errors) < 10:
            return 20.0
        within = sum(1 for e in errors if e <= 10.0)
        return 10.0 if within >= 10 else 20.0

    def _recent_prediction_errors(self, limit: int = 10) -> list[float]:
        history = self.metrics.get_metric_history("prediction_error_pct")
        return [v for _, v in history[-limit:]]

    def _sessions_matching(
        self,
        session_type: str,
        phase_id: str | None,
        complexity: TaskComplexity | None = None,
    ) -> list[float]:
        with self.metrics._connect() as conn:
            rows = conn.execute(
                """
                SELECT value, tags FROM metrics
                WHERE metric_name = 'tokens_per_session'
                ORDER BY timestamp DESC
                LIMIT 500
                """
            ).fetchall()

        results: list[float] = []
        for row in rows:
            tags_raw = row["tags"]
            try:
                tags = json.loads(tags_raw) if tags_raw else {}
            except json.JSONDecodeError:
                tags = {}
            if tags.get("session_type") != session_type:
                continue
            if phase_id is not None and tags.get("phase_id") != phase_id:
                continue
            if complexity is not None and tags.get("complexity") != complexity:
                continue
            results.append(float(row["value"]))
        return results
