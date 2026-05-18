"""Agent permission categories and session-scoped grants."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

PERM_DELETE = "delete"
PERM_SHELL = "shell"

SESSION_GRANTS_KEY = "agent_grants"


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    remember_session: bool = False


def permission_for_command(cmd_line: str) -> tuple[str | None, str]:
    """Return (permission_category, human_detail) if command needs approval."""
    line = cmd_line.strip()
    if not line:
        return None, ""
    lower = line.lower()
    for pat in (
        r"rm\s+-rf",
        r"rm\s+--no-preserve-root",
        r"rm\s+-r\s+/",
        r"rm\s+-fr\s+/",
    ):
        if re.search(pat, lower):
            return PERM_DELETE, f"Blocked dangerous command: {line[:120]}"
    segments = re.split(r"\s*(?:\||&&|\|\|)\s*", line)
    for segment in segments:
        seg = segment.strip()
        if not seg:
            continue
        try:
            parts = shlex.split(seg)
        except ValueError:
            continue
        if not parts:
            continue
        base = parts[0].lower()
        if base in ("rm", "unlink"):
            return PERM_DELETE, f"Shell delete: {line[:160]}"
    return None, ""


def permission_for_tool(tool_name: str, args: dict) -> tuple[str | None, str]:
    if tool_name == "delete_file":
        path = str(args.get("path", ""))
        return PERM_DELETE, f"Delete file: {path}"
    return None, ""


def grants_from_session_state(state: dict | None) -> set[str]:
    if not state:
        return set()
    raw = state.get(SESSION_GRANTS_KEY) or []
    return {str(x) for x in raw if x}


def merge_grants_into_session(state: dict | None, grants: set[str]) -> dict:
    data = dict(state or {})
    data[SESSION_GRANTS_KEY] = sorted(grants)
    return data
