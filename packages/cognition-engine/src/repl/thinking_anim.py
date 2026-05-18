"""Compact thinking indicator for the REPL."""

from __future__ import annotations

from src.repl.markup_safe import escape_markup

_BRAILLE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


def thinking_panel_markup(tick: int, *, status: str = "") -> str:
    """Small professional thinking line (fits narrow chat column)."""
    b = _BRAILLE[tick % len(_BRAILLE)]
    st = escape_markup(status) if status else "Working…"
    return (
        f"[bold #6cb6ff]{b}[/] [italic]Thinking[/]  "
        f"[white]{st}[/]"
    )


def thinking_trace_line(tick: int, *, status: str = "") -> str:
    b = _BRAILLE[tick % len(_BRAILLE)]
    st = escape_markup(status) if status else "…"
    return f"[bold #6cb6ff]{b}[/] [dim]{st}[/]"
