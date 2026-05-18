"""Format agent trace lines — compact, no horizontal overflow."""

from __future__ import annotations

from src.repl.markup_safe import escape_markup

_TRACE_RULES: list[tuple[str, str, str]] = [
    ("shield", "SHIELD", "#d2a8ff"),
    ("writing file", "WRITE", "#ffa657"),
    ("write result", "WRITE", "#ffa657"),
    ("reading file", "READ", "#3fb950"),
    ("listing directory", "LIST", "#3fb950"),
    ("running command", "RUN", "#ffa657"),
    ("command output", "RUN", "#ffa657"),
    ("model step", "STEP", "#79c0ff"),
    ("agentic mode", "AGENT", "#79c0ff"),
    ("editing file", "EDIT", "#ffa657"),
    ("executing shell", "RUN", "#ffa657"),
    ("tool", "TOOL", "#ffa657"),
    ("tokens", "TOK", "#e3b341"),
    ("calling", "MODEL", "#79c0ff"),
    ("waiting", "NET", "#6cb6ff"),
    ("response", "NET", "#6cb6ff"),
    ("loading", "CTX", "#3fb950"),
    ("parsing", "PARSE", "#e3b341"),
    ("done", "OK", "#3fb950"),
]


def trace_lane_markup(text: str) -> str:
    lower = text.lower()
    lane = "WORK"
    color = "#8b949e"
    for needle, name, col in _TRACE_RULES:
        if needle in lower:
            lane = name
            color = col
            break
    safe = escape_markup(text)
    if len(safe) > 72:
        safe = safe[:69] + "…"
    return f"[bold {color}]{lane:5}[/] [white]{safe}[/]"
