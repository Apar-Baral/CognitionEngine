"""Decide quick chat vs full agentic tool loop."""

from __future__ import annotations

import re

# User clearly wants filesystem / shell / multi-step work
_AGENTIC_PATTERNS = re.compile(
    r"\b("
    r"create|write|delete|remove|add|generate|build|implement|fix|refactor|"
    r"scaffold|install|deploy|run|execute|command|script|tool|payload|"
    r"files?|folder|directory|project|repo|codebase|grep|find|mkdir|"
    r"read_file|write_file|list_dir|commit|push|pull|test|pytest|"
    r"all\s+\d+|every\s+file|each\s+file|multiple\s+files|"
    r"in\s+this\s+(dir|folder|project)|under\s+payloads"
    r")\b",
    re.IGNORECASE,
)

_EXPLICIT_AGENTIC = re.compile(
    r"\b(use\s+tools?|agentic|run\s+tools?|with\s+tools?)\b",
    re.IGNORECASE,
)


def is_agentic_request(message: str) -> bool:
    """True when the user likely needs tools / multi-step agent work."""
    text = message.strip()
    if not text:
        return False
    if _EXPLICIT_AGENTIC.search(text):
        return True
    if len(text) > 220:
        return True
    if _AGENTIC_PATTERNS.search(text):
        return True
    # Multiple sentences often imply a task brief
    if text.count(".") >= 2 and len(text) > 80:
        return True
    return False
