"""
Runaway detection — anomalies and repeated non-progress patterns.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from src.proxy.budget_enforcer import BudgetEnforcer

logger = logging.getLogger(__name__)

WINDOW_SIZE = 20
ANOMALY_WINDOW_MINUTES = 2
ANOMALY_THRESHOLD = 3


class RunawayDetector:
    """Detect runaway token consumption and take escalating action."""

    def __init__(
        self,
        api_call_log: list[dict[str, Any]],
        budget_enforcer: BudgetEnforcer,
    ) -> None:
        self.api_call_log = api_call_log
        self.budget_enforcer = budget_enforcer
        self._token_window: deque[int] = deque(maxlen=WINDOW_SIZE)
        self._anomaly_times: deque[datetime] = deque()
        self._runaway_count = 0
        self._user_overrides = 0
        self._user_confirmations = 0
        self._sensitivity = 3.0
        self._history: list[dict[str, Any]] = []

    def monitor_request(
        self,
        request: dict[str, Any],
        response: dict[str, Any],
        *,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        total = input_tokens + output_tokens
        self._token_window.append(total)
        self.api_call_log.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "request": request,
                "response": response,
                "tokens": total,
            }
        )

        is_anomaly, desc = self.check_anomaly(total)
        if is_anomaly:
            self._anomaly_times.append(datetime.now(timezone.utc))
            self._history.append({"type": "anomaly", "description": desc, "tokens": total})

    def check_anomaly(self, token_count: int | None = None) -> tuple[bool, str]:
        if token_count is None:
            if not self._token_window:
                return False, ""
            token_count = self._token_window[-1]
        if len(self._token_window) < 3:
            return False, ""

        values = list(self._token_window)
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std = variance**0.5
        threshold = mean + self._sensitivity * std
        if std > 0 and token_count > threshold:
            return True, f"Token count {token_count} exceeds mean+{self._sensitivity}σ ({threshold:.0f})"
        return False, ""

    def detect_runaway_condition(self) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(minutes=ANOMALY_WINDOW_MINUTES)
        recent_anomalies = sum(1 for t in self._anomaly_times if t >= cutoff)
        if recent_anomalies >= ANOMALY_THRESHOLD:
            return (
                True,
                f"{recent_anomalies} anomalies in the last {ANOMALY_WINDOW_MINUTES} minutes",
            )

        if len(self._token_window) >= 6:
            last_six = list(self._token_window)[-6:]
            if max(last_six) > 2 * min(last_six) and sum(last_six) / len(last_six) > 5000:
                return True, "Sustained high token usage without progress signals"

        return False, ""

    def on_runaway_detected(self) -> dict[str, Any]:
        self._runaway_count += 1
        severity = self._runaway_count
        action: dict[str, Any] = {
            "severity": severity,
            "runaway_count": self._runaway_count,
        }

        if severity == 1:
            action["inject_message"] = (
                "Pause and re-evaluate your approach. You may be consuming tokens without progress."
            )
            action["pause_session"] = False
        elif severity == 2:
            action["inject_message"] = (
                "Runaway usage detected. Complete current work and prepare to wrap up immediately."
            )
            self.budget_enforcer.wrap_up_mode = True
            action["force_wrap_up"] = True
            action["pause_session"] = False
        else:
            action["inject_message"] = "Session paused due to runaway token usage."
            action["pause_session"] = True
            action["alert_user"] = True

        self._history.append({"type": "runaway", **action})
        return action

    def record_user_override(self, was_false_positive: bool) -> None:
        if was_false_positive:
            self._user_overrides += 1
            self._sensitivity = min(4.5, self._sensitivity + 0.2)
            self._runaway_count = max(0, self._runaway_count - 1)
        else:
            self._user_confirmations += 1
            self._sensitivity = max(2.0, self._sensitivity - 0.2)

    def get_runaway_stats(self) -> dict[str, Any]:
        return {
            "session_runaway_alerts": self._runaway_count,
            "anomalies_logged": len(self._history),
            "user_overrides": self._user_overrides,
            "user_confirmations": self._user_confirmations,
            "sensitivity_sigma": self._sensitivity,
            "history": self._history[-20:],
        }
