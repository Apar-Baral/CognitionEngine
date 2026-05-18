"""Clean model output for chat display (no DSML / raw tool JSON)."""

from __future__ import annotations

import re

from src.agent.dsml_parser import strip_dsml_markup


def clean_assistant_text(text: str) -> str:
    """User-visible assistant message without DSML or bare tool JSON."""
    if not text:
        return ""
    out = strip_dsml_markup(text)
    # Remove lone JSON tool lines
    lines: list[str] = []
    for line in out.splitlines():
        s = line.strip()
        if s.startswith('{"tool"') and s.endswith("}"):
            continue
        if s.startswith("```") and "tool" in s.lower():
            continue
        lines.append(line)
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
