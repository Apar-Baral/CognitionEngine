from __future__ import annotations

from typing import Any

from cognition_engine.core.constants import (
    DEFAULT_SESSION_BUDGETS,
    BudgetZone,
    SessionType,
)


class BudgetTracker:
    def __init__(self, dna: dict[str, Any]) -> None:
        self.dna = dna

    def session_budget(self) -> int:
        budget = self.dna.get("budget", {})
        return int(budget.get("session_budget_tokens", DEFAULT_SESSION_BUDGETS[SessionType.BUILD]))

    def tokens_used(self) -> int:
        return int(self.dna.get("budget", {}).get("tokens_consumed_this_session", 0))

    def ratio(self) -> float:
        total = self.session_budget()
        if total <= 0:
            return 0.0
        return self.tokens_used() / total

    def zone(self, used: int | None = None, total: int | None = None) -> BudgetZone:
        u = used if used is not None else self.tokens_used()
        t = total if total is not None else self.session_budget()
        if t <= 0:
            return BudgetZone.GREEN
        r = u / t
        if r < 0.60:
            return BudgetZone.GREEN
        if r < 0.85:
            return BudgetZone.YELLOW
        return BudgetZone.RED

    def status_lines(self) -> list[str]:
        used = self.tokens_used()
        total = self.session_budget()
        zone = self.zone(used, total)
        pct = round(100 * used / total, 1) if total else 0
        remaining = max(0, total - used)
        st = self.dna.get("budget", {}).get("session_type", "BUILD")
        return [
            f"Session type: {st}",
            f"Budget: {used:,} / {total:,} tokens ({pct}%)",
            f"Zone: {zone.value.upper()}",
            f"Remaining: {remaining:,} tokens",
        ]

    def check_budget(self, additional: int = 0) -> tuple[bool, str]:
        used = self.tokens_used() + additional
        total = self.session_budget()
        if used >= total:
            return False, f"Token budget exceeded ({used:,} >= {total:,})"
        z = self.zone(used, total)
        if z == BudgetZone.RED:
            return True, f"WARNING: RED zone ({used:,}/{total:,}) — wrap up soon"
        if z == BudgetZone.YELLOW:
            return True, f"WARNING: YELLOW zone ({used:,}/{total:,})"
        return True, "OK"
