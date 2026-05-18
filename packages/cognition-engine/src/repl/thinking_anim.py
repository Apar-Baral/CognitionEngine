"""Claude Code–style thinking / imagining animation frames for the REPL."""

from __future__ import annotations

_THINK_PHASES = (
    "Reading project context",
    "Tracing dependencies",
    "Imagining approaches",
    "Calling the model",
    "Weaving a response",
    "Validating with shield",
)

_BRAILLE = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPARKS = ("✦", "✧", "⋆", "✵", "✶", "✷")


def phase_for_tick(tick: int) -> str:
    return _THINK_PHASES[(tick // 6) % len(_THINK_PHASES)]


def _scan_bar(tick: int, width: int = 22) -> str:
    pos = tick % width
    left = "─" * pos
    right = "─" * (width - pos - 1)
    return f"[dim]{left}[/][bold #6cb6ff]◉[/][dim]{right}[/]"


def _orbit(tick: int) -> str:
    """Three sparks orbiting a center glyph."""
    slots = ["·", "·", "·", "·", "·", "·", "·", "·"]
    a, b, c = tick % 8, (tick + 3) % 8, (tick + 5) % 8
    s = _SPARKS[tick % len(_SPARKS)]
    slots[a] = f"[bold #6cb6ff]{s}[/]"
    slots[b] = f"[#79c0ff]{_BRAILLE[tick % len(_BRAILLE)]}[/]"
    slots[c] = f"[bold #d2a8ff]{_SPARKS[(tick + 2) % len(_SPARKS)]}[/]"
    return "".join(slots)


def thinking_panel_markup(tick: int) -> str:
    """Large animated panel shown while the agent works."""
    b = _BRAILLE[tick % len(_BRAILLE)]
    b2 = _BRAILLE[(tick + 3) % len(_BRAILLE)]
    phase = phase_for_tick(tick)
    orbit = _orbit(tick)
    bar = _scan_bar(tick)
    pulse = ("▁", "▂", "▃", "▄", "▅", "▆", "▇", "█")[tick % 8]
    wave = ("∿", "≈", "∽", "≋")[(tick // 2) % 4]

    return (
        f"[bold #58a6ff]╭─ {wave} imagining {wave} ─────────────────────╮[/]\n"
        f"[bold #58a6ff]│[/]  {orbit}  [bold white]{b}[/][dim]···[/][bold white]{b2}[/]  {orbit}  "
        f"[bold #58a6ff]│[/]\n"
        f"[bold #58a6ff]│[/]  {bar}  [bold #58a6ff]│[/]\n"
        f"[bold #58a6ff]│[/]  [italic #79c0ff]{phase}[/]  [dim]{pulse * 3}[/]  "
        f"[bold #58a6ff]│[/]\n"
        f"[bold #58a6ff]╰──────────────────────────────────────────╯[/]"
    )


def thinking_trace_line(tick: int) -> str:
    """Compact line for the trace rail."""
    b = _BRAILLE[tick % len(_BRAILLE)]
    phase = phase_for_tick(tick)
    return f"[bold #6cb6ff]{b}[/] [italic]{phase}[/] [dim]· imagining…[/]"
