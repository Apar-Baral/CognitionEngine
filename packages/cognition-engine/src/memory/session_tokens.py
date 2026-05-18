"""Normalize token counts from heterogeneous session record shapes."""

from __future__ import annotations

from typing import Any


def session_tokens_consumed(session: dict[str, Any]) -> int:
    """Resolve token count from session index, store, or operational summary shapes."""
    raw = session.get("tokens_consumed")
    if raw is None:
        raw = session.get("tokens")
    if isinstance(raw, dict):
        return int(raw.get("total", 0) or 0)
    if raw is None:
        return 0
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0
