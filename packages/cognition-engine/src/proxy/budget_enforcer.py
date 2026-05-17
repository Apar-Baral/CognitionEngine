"""
Budget enforcement with GREEN / YELLOW / RED / WRAP_UP / EXHAUSTED zones.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.core.constants import BudgetZone, budget_zone_for_ratio

logger = logging.getLogger(__name__)

WRAP_UP_GRACE_RATIO = 1.05

ZONE_MESSAGES: dict[BudgetZone, str] = {
    BudgetZone.YELLOW: (
        "You have consumed over 60% of the token budget for this session. "
        "Continue working but prefer concise responses. Avoid unnecessary file re-reads."
    ),
    BudgetZone.RED: (
        "Token budget is critically low. Complete your current sub-task. "
        "Do NOT start any new work. Be as concise as possible."
    ),
    BudgetZone.WRAP_UP: (
        "Session budget is at 90%. You must now complete your immediate task and "
        "produce a SESSION HANDOFF SUMMARY. The handoff must include: exactly what was "
        "accomplished this session, what is partially complete and the exact file and line "
        "to resume from, any decisions made and their rationale, any new discoveries or "
        "gotchas, and a recommended next sub-task. Do not start any new tasks. Focus only "
        "on wrapping up and producing this summary."
    ),
}


class BudgetEnforcer:
    """Enforce session token budget with graceful wrap-up."""

    def __init__(
        self,
        budget_limit: int,
        cost_limit: float | None = None,
    ) -> None:
        self.budget_limit = budget_limit
        self.cost_limit = cost_limit
        self.tokens_used = 0
        self.cost_incurred = 0.0
        self.wrap_up_mode = False
        self.wrap_up_triggered_at: datetime | None = None
        self._pending_injection: str | None = None
        self._last_zone = BudgetZone.GREEN
        self._override_events: list[dict[str, Any]] = []
        self._session_start = datetime.now(timezone.utc)

    def check_budget(self, tokens_used: int | None = None) -> dict[str, Any]:
        used = self.tokens_used if tokens_used is None else tokens_used
        ratio = used / self.budget_limit if self.budget_limit > 0 else 0.0
        zone = budget_zone_for_ratio(ratio)

        if zone == BudgetZone.WRAP_UP:
            self.wrap_up_mode = True
            if self.wrap_up_triggered_at is None:
                self.wrap_up_triggered_at = datetime.now(timezone.utc)

        inject = False
        inject_text: str | None = None
        warning: str | None = None
        continue_session = True
        wrap_up_flag = zone == BudgetZone.WRAP_UP or self.wrap_up_mode

        if zone == BudgetZone.EXHAUSTED or ratio >= 1.0:
            if self.wrap_up_mode and used < self.budget_limit * WRAP_UP_GRACE_RATIO:
                continue_session = True
                warning = "Budget exceeded during wrap-up grace window."
            else:
                continue_session = False
                warning = (
                    f"Token budget exhausted ({used:,} / {self.budget_limit:,}). "
                    "No further API calls allowed."
                )
        elif zone == BudgetZone.YELLOW:
            warning = f"YELLOW zone: {ratio * 100:.1f}% of budget used."
            if zone != self._last_zone:
                inject = True
                inject_text = self.get_zone_message(zone)
        elif zone == BudgetZone.RED:
            warning = f"RED zone: {ratio * 100:.1f}% of budget used — finish current work."
            if zone != self._last_zone:
                inject = True
                inject_text = self.get_zone_message(zone)
        elif zone == BudgetZone.WRAP_UP:
            warning = "WRAP_UP zone: produce session handoff summary."
            if zone != self._last_zone or not self._pending_injection:
                inject = True
                inject_text = self.get_zone_message(zone)

        if inject and inject_text:
            self._pending_injection = inject_text

        self._last_zone = zone

        return {
            "zone": zone.value,
            "tokens_used": used,
            "tokens_remaining": max(0, self.budget_limit - used),
            "percentage_used": round(ratio * 100, 2),
            "continue": continue_session,
            "warning": warning,
            "inject_system_message": inject,
            "system_message": inject_text,
            "wrap_up": wrap_up_flag,
        }

    def consume_pending_injection(self) -> str | None:
        msg = self._pending_injection
        self._pending_injection = None
        return msg

    def should_block_new_task(self, request_body: dict[str, Any]) -> bool:
        """During wrap-up, block tool calls that look like new work."""
        if not self.wrap_up_mode:
            return False
        tools = request_body.get("tools") or []
        messages = request_body.get("messages", [])
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = str(msg.get("content", "")).lower()
                break
        new_work_hints = ("create new", "start new", "implement new feature", "new task")
        if any(h in last_user for h in new_work_hints):
            return True
        if len(tools) > 0 and self.tokens_used >= self.budget_limit * 0.95:
            return True
        return False

    def get_budget_status(
        self,
        *,
        burn_rate_tokens_per_minute: float | None = None,
    ) -> dict[str, Any]:
        check = self.check_budget()
        elapsed = (datetime.now(timezone.utc) - self._session_start).total_seconds()
        rate = burn_rate_tokens_per_minute
        if rate is None and elapsed > 0:
            rate = self.tokens_used / (elapsed / 60.0)
        remaining_tokens = check["tokens_remaining"]
        eta_minutes = None
        if rate and rate > 0:
            eta_minutes = remaining_tokens / rate

        return {
            **check,
            "budget_limit": self.budget_limit,
            "burn_rate_per_minute": round(rate or 0, 2),
            "estimated_minutes_remaining": round(eta_minutes, 2) if eta_minutes else None,
            "cost_incurred": round(self.cost_incurred, 4),
            "zone_color": check["zone"],
            "wrap_up_mode": self.wrap_up_mode,
        }

    def should_wrap_up(self) -> bool:
        return self.wrap_up_mode or budget_zone_for_ratio(
            self.tokens_used / self.budget_limit if self.budget_limit else 0
        ) in (BudgetZone.WRAP_UP, BudgetZone.EXHAUSTED)

    def is_exhausted(self) -> bool:
        if self.budget_limit <= 0:
            return False
        ratio = self.tokens_used / self.budget_limit
        if ratio < 1.0:
            return False
        if self.wrap_up_mode and self.tokens_used < self.budget_limit * WRAP_UP_GRACE_RATIO:
            return False
        return True

    def get_zone_message(self, zone: BudgetZone | str) -> str:
        if isinstance(zone, str):
            try:
                zone = BudgetZone(zone)
            except ValueError:
                return ""
        return ZONE_MESSAGES.get(zone, "")

    def add_tokens(self, amount: int, reason: str = "user_override") -> None:
        self.budget_limit += amount
        self._override_events.append(
            {
                "amount": amount,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "new_limit": self.budget_limit,
            }
        )
        logger.info("Budget override: +%s tokens (%s)", amount, reason)

    def get_remaining_budget(self) -> int:
        return max(0, self.budget_limit - self.tokens_used)

    def add_usage(self, tokens: int, cost: float = 0.0) -> None:
        self.tokens_used += tokens
        self.cost_incurred += cost
