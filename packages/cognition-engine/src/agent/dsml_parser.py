"""Parse DeepSeek DSML tool markup and strip it from user-visible text."""

from __future__ import annotations

import re
from typing import Any

# DeepSeek: <|DSML|invoke> or < | | DSML | | invoke> (spaces vary)
_DSML_BLOCK = re.compile(
    r"<\s*/?\s*(?:\|\s*)+DSML(?:\s*\|)+\s*\w+[^>]*>.*?"
    r"<\s*/\s*(?:\|\s*)+DSML(?:\s*\|)+\s*\w+\s*>",
    re.IGNORECASE | re.DOTALL,
)
_INVOKE = re.compile(
    r"<\s*/?\s*(?:\|\s*)+DSML(?:\s*\|)+\s*invoke\s+name\s*=\s*\"([^\"]+)\"\s*>"
    r"(.*?)"
    r"<\s*/\s*(?:\|\s*)+DSML(?:\s*\|)+\s*invoke\s*>",
    re.IGNORECASE | re.DOTALL,
)
_PARAM = re.compile(
    r"<\s*/?\s*(?:\|\s*)+DSML(?:\s*\|)+\s*parameter\s+name\s*=\s*\"([^\"]+)\""
    r"(?:\s+string\s*=\s*\"[^\"]*\")?\s*>"
    r"(.*?)"
    r"<\s*/\s*(?:\|\s*)+DSML(?:\s*\|)+\s*parameter\s*>",
    re.IGNORECASE | re.DOTALL,
)
# Compact fallback: <|DSML|invoke name="tool">
_INVOKE_COMPACT = re.compile(
    r"<\s*\|?\s*DSML\s*\|+\s*invoke\s+name\s*=\s*\"([^\"]+)\"\s*>"
    r"(.*?)"
    r"<\s*/\s*\|?\s*DSML\s*\|+\s*invoke\s*>",
    re.IGNORECASE | re.DOTALL,
)
_PARAM_COMPACT = re.compile(
    r"<\s*\|?\s*DSML\s*\|+\s*parameter\s+name\s*=\s*\"([^\"]+)\""
    r"(?:\s+string\s*=\s*\"[^\"]*\")?\s*>"
    r"(.*?)"
    r"<\s*/\s*\|?\s*DSML\s*\|+\s*parameter\s*>",
    re.IGNORECASE | re.DOTALL,
)
_ANY_DSML = re.compile(
    r"<\s*/?\s*(?:\|\s*)*DSML(?:\s*\|)+[^>]*>",
    re.IGNORECASE,
)


def strip_dsml_markup(text: str) -> str:
    """Remove DSML/XML tool blocks from text shown in chat."""
    if not text or "dsml" not in text.lower():
        return text
    cleaned = _DSML_BLOCK.sub("", text)
    cleaned = _ANY_DSML.sub("", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _parse_invoke(match: re.Match[str]) -> dict[str, Any]:
    tool_name = match.group(1).strip()
    body = match.group(2)
    args: dict[str, str] = {}
    for pm in _PARAM.finditer(body):
        args[pm.group(1).strip()] = pm.group(2).strip()
    for pm in _PARAM_COMPACT.finditer(body):
        args[pm.group(1).strip()] = pm.group(2).strip()
    if tool_name == "list_dir" and "path" not in args:
        args["path"] = "."
    if tool_name == "run_command" and "cmd" not in args and "command" in args:
        args["cmd"] = args.pop("command")
    return {"tool": tool_name, "args": args}


def extract_dsml_tool_calls(text: str) -> list[dict[str, Any]]:
    """Convert DSML invoke blocks to CE tool-call dicts."""
    if not text or "dsml" not in text.lower():
        return []
    calls: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pattern in (_INVOKE, _INVOKE_COMPACT):
        for match in pattern.finditer(text):
            call = _parse_invoke(match)
            key = f"{call['tool']}:{call.get('args')}"
            if key not in seen:
                seen.add(key)
                calls.append(call)
    return calls
