"""Claude Code–style thinking box for the REPL."""

from __future__ import annotations

from src.repl.markup_safe import escape_markup

_BRAILLE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_WAVE = ("∿", "≈", "∽")


def thinking_box_markup(tick: int, *, status: str = "", recent: list[str] | None = None) -> tuple[str, str]:
    """Header line + detail block for the thinking box."""
    b = _BRAILLE[tick % len(_BRAILLE)]
    w = _WAVE[tick % len(_WAVE)]
    st = escape_markup(status) if status else "Working on your request…"
    header = (
        f"[bold #58a6ff]╭─[/] {w} [bold #6cb6ff]Thinking[/] {w} [bold #58a6ff]─╮[/]\n"
        f"[bold #58a6ff]│[/] [bold white]{b}[/] [italic]{st}[/]"
    )
    lines = [header]
    for item in (recent or [])[-4:]:
        lines.append(f"\n[bold #58a6ff]│[/] [dim]·[/] [white]{escape_markup(item)}[/]")
    lines.append("\n[bold #58a6ff]╰──────────────────────────────╯[/]")
    return header, "".join(lines)


def thinking_panel_markup(tick: int, *, status: str = "") -> str:
    """Legacy single-line (typing strip)."""
    b = _BRAILLE[tick % len(_BRAILLE)]
    st = escape_markup(status) if status else "Working…"
    return f"[bold #6cb6ff]{b}[/] [italic]typing…[/] [white]{st}[/]"


def thinking_trace_line(tick: int, *, status: str = "") -> str:
    b = _BRAILLE[tick % len(_BRAILLE)]
    st = escape_markup(status) if status else "…"
    return f"[bold #6cb6ff]{b}[/] {st}"
