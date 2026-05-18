"""Dynamic live agent panel — stream, plans, and trace (not static placeholders)."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.repl.markup_safe import escape_markup

_BRAILLE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


@dataclass
class LiveAgentView:
    step: int = 0
    max_steps: int = 40
    status: str = ""
    stream: str = ""
    planned: list[str] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)


def live_thinking_markup(tick: int, view: LiveAgentView) -> tuple[str, str]:
    b = _BRAILLE[tick % len(_BRAILLE)]
    st = escape_markup(view.status or "Working…")
    step_line = ""
    if view.step > 0:
        step_line = f" · step {view.step}/{view.max_steps}"
    header = (
        f"[bold #58a6ff]╭─[/] [bold #6cb6ff]{b} Live agent[/]{step_line} [bold #58a6ff]─╮[/]\n"
        f"[bold #58a6ff]│[/] [italic white]{st}[/]"
    )
    lines = [header]

    if view.planned:
        lines.append("\n[bold #58a6ff]│[/] [bold #e3b341]Will do next[/]")
        for item in view.planned[-6:]:
            lines.append(f"\n[bold #58a6ff]│[/]   [yellow]▸[/] [white]{escape_markup(item)}[/]")

    if view.stream.strip():
        preview = view.stream.strip()
        if len(preview) > 1200:
            preview = "…" + preview[-1197:]
        for line in preview.split("\n")[-14:]:
            lines.append(f"\n[bold #58a6ff]│[/] [dim cyan]{escape_markup(line)}[/]")

    if view.trace:
        lines.append("\n[bold #58a6ff]│[/] [bold #3fb950]Trace[/]")
        for item in view.trace[-10:]:
            lines.append(f"\n[bold #58a6ff]│[/] [dim]·[/] [white]{escape_markup(item)}[/]")

    lines.append("\n[bold #58a6ff]╰──────────────────────────────╯[/]")
    return header, "".join(lines)
