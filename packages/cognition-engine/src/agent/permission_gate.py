"""Session permission grants with optional UI callback."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.agent.permissions import (
    SESSION_GRANTS_KEY,
    PermissionDecision,
    grants_from_session_state,
    merge_grants_into_session,
)

logger = logging.getLogger(__name__)

PermissionCallback = Callable[[str, str], PermissionDecision]


class SessionPermissionGate:
    """Tracks grants for the active CE session; persists to active_session.json."""

    def __init__(
        self,
        ctx: Any,
        *,
        on_request: PermissionCallback | None = None,
        on_activity: Callable[[str], None] | None = None,
    ) -> None:
        self.ctx = ctx
        self._on_request = on_request
        self._on_activity = on_activity or (lambda _m: None)
        self._grants: set[str] = grants_from_session_state(ctx.load_session_state())

    @property
    def grants(self) -> frozenset[str]:
        return frozenset(self._grants)

    def reload(self) -> None:
        self._grants = grants_from_session_state(self.ctx.load_session_state())

    def clear(self) -> None:
        self._grants = set()
        state = self.ctx.load_session_state()
        if state and SESSION_GRANTS_KEY in state:
            data = dict(state)
            data.pop(SESSION_GRANTS_KEY, None)
            self.ctx.save_session_state(data)

    def ensure(self, category: str, detail: str) -> bool:
        if category in self._grants:
            return True
        if not self._on_request:
            self._on_activity(f"Permission required ({category}) — no UI; denied")
            return False
        self._on_activity(f"Permission required: {detail}")
        try:
            decision = self._on_request(category, detail)
        except Exception:
            logger.debug("permission callback failed", exc_info=True)
            return False
        if not decision.allowed:
            self._on_activity(f"Permission denied: {category}")
            return False
        if decision.remember_session:
            self._grants.add(category)
            state = merge_grants_into_session(self.ctx.load_session_state(), self._grants)
            self.ctx.save_session_state(state)
            self._on_activity(f"Permission granted for session: {category}")
        else:
            self._on_activity(f"Permission granted once: {category}")
        return True
