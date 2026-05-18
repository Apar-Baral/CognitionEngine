"""Human-readable descriptions of agent steps (dynamic trace, not static tips)."""

from __future__ import annotations

from typing import Any


def describe_tool_call(call: dict[str, Any]) -> str:
    name = str(call.get("tool", "?"))
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    if name == "write_file":
        path = args.get("path", "?")
        n = len(str(args.get("content", "")))
        return f"WRITE {path} ({n} bytes)"
    if name == "read_file":
        return f"READ {args.get('path', '?')}"
    if name == "list_dir":
        return f"LIST {args.get('path', '.')}"
    if name == "delete_file":
        return f"DELETE {args.get('path', '?')}"
    if name == "run_command":
        cmd = str(args.get("cmd", ""))
        if len(cmd) > 72:
            cmd = cmd[:69] + "…"
        return f"RUN {cmd}"
    if name == "suggest_next":
        return "SUGGEST next steps"
    return f"{name.upper()} {args}"


def classify_activity(msg: str) -> str:
    lower = msg.lower()
    if "streaming" in lower or "waiting for model" in lower:
        return "model"
    if "planned" in lower or "next action" in lower:
        return "plan"
    if "permission" in lower:
        return "perm"
    if any(x in lower for x in ("writing file", "deleting", "reading file", "listing", "running command")):
        return "exec"
    if lower.startswith("✓") or "done:" in lower:
        return "done"
    if "model step" in lower:
        return "step"
    return "info"
