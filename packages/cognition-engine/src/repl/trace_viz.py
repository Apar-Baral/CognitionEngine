"""Format agent trace lines for the REPL (structured, not plain bullets)."""

from __future__ import annotations

from src.repl.markup_safe import escape_markup

_TRACE_RULES: list[tuple[str, str, str]] = [
    ("shield", "SHIELD", "#d2a8ff"),
    ("tool", "TOOL", "#ffa657"),
    ("running tool", "TOOL", "#ffa657"),
    ("validating", "SHIELD", "#d2a8ff"),
    ("calling", "MODEL", "#79c0ff"),
    ("waiting", "NETWORK", "#6cb6ff"),
    ("response received", "NETWORK", "#6cb6ff"),
    ("loading", "CONTEXT", "#3fb950"),
    ("context", "CONTEXT", "#3fb950"),
    ("parsing", "PARSE", "#e3b341"),
    ("computing", "PLAN", "#e3b341"),
    ("starting", "START", "#58a6ff"),
    ("done", "DONE", "#3fb950"),
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
    return (
        f"[dim]╭─[/][bold {color}] {lane} [/][dim]────────────────[/]\n"
        f"[white]  {safe}[/]\n"
        f"[dim]╰────────────────────────────────[/]"
    )
