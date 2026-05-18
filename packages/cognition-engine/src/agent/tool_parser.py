"""Extract tool-call JSON from model responses (markdown fences, arrays, etc.)."""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_TOOL_KEY = re.compile(r'\{\s*"tool"\s*:', re.IGNORECASE)


def _parse_object(raw: str) -> dict[str, Any] | None:
    raw = raw.strip()
    if not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data, _end = json.JSONDecoder().raw_decode(raw)
        except json.JSONDecodeError:
            return None
    if isinstance(data, dict) and "tool" in data:
        return data
    return None


def extract_tool_calls(text: str) -> list[dict[str, Any]]:
    """Return zero or more tool call dicts from assistant text."""
    if not text or not text.strip():
        return []
    from src.agent.dsml_parser import extract_dsml_tool_calls

    found: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(obj: dict[str, Any] | None) -> None:
        if not obj or "tool" not in obj:
            return
        key = json.dumps(obj, sort_keys=True, default=str)
        if key not in seen:
            seen.add(key)
            found.append(obj)

    for dsml_call in extract_dsml_tool_calls(text):
        add(dsml_call)
    if found:
        return found

    whole = text.strip()
    if whole.startswith("["):
        try:
            arr = json.loads(whole)
            if isinstance(arr, list):
                for item in arr:
                    if isinstance(item, dict):
                        add(item)
                if found:
                    return found
        except json.JSONDecodeError:
            pass

    add(_parse_object(whole))

    for match in _FENCE.finditer(text):
        add(_parse_object(match.group(1)))

    for match in _TOOL_KEY.finditer(text):
        chunk = text[match.start() :]
        add(_parse_object(chunk))

    return found
