"""
Reward function for RL token allocation learning.
"""

from __future__ import annotations

from typing import Any


class RewardCalculator:
    """Compute session reward from outcome metrics."""

    def calculate_reward(self, outcome: dict[str, Any]) -> float:
        efficiency = self._efficiency_score(outcome)
        budget = self._budget_adherence_score(outcome)
        quality = self._code_quality_score(outcome)
        completion = self._completion_score(outcome)
        raw = efficiency * 0.4 + budget * 0.3 + quality * 0.2 + completion * 0.1
        return self.normalize_reward(raw)

    @staticmethod
    def normalize_reward(value: float) -> float:
        return max(0.0, min(100.0, float(value)))

    def _efficiency_score(self, outcome: dict[str, Any]) -> float:
        lines = float(outcome.get("lines_accepted", outcome.get("files_modified_count", 0) * 20))
        tokens = float(outcome.get("tokens_consumed", outcome.get("total_tokens", 1)) or 1)
        baseline = 0.05
        ratio = lines / tokens
        return min(100.0, (ratio / baseline) * 50)

    def _budget_adherence_score(self, outcome: dict[str, Any]) -> float:
        used = float(outcome.get("tokens_consumed", 0))
        budget = float(outcome.get("token_budget", used) or used)
        if budget <= 0:
            return 80.0
        ratio = used / budget
        if 0.95 <= ratio <= 1.0:
            return 100.0
        if 0.8 <= ratio < 0.95:
            return 90.0
        if ratio < 0.5:
            return 50.0
        if ratio <= 1.1:
            return 50.0
        if ratio <= 1.25:
            return 25.0
        return 0.0

    def _code_quality_score(self, outcome: dict[str, Any]) -> float:
        hall_rate = float(outcome.get("hallucination_rate", 0))
        shield_flags = int(outcome.get("shield_flags", 0))
        score = 100.0 - hall_rate * 100 - shield_flags * 5
        if outcome.get("tests_passing"):
            score = min(100.0, score + 10)
        return max(0.0, score)

    def _completion_score(self, outcome: dict[str, Any]) -> float:
        if outcome.get("sub_task_completed"):
            return 100.0
        prog = float(outcome.get("progress_made", outcome.get("efficiency_score", 0)))
        if prog >= 70:
            return 70.0
        if prog >= 40:
            return 40.0
        return 0.0
