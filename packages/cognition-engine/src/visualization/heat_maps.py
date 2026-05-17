"""
Token consumption heat maps for terminal display.
"""

from __future__ import annotations

from typing import Any

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from src.visualization import ascii_art as art


def render_token_heat_map(
    file_tokens: dict[str, int],
    *,
    title: str = "Token Consumption Heat Map",
) -> RenderableType:
    """Treemap-style rows: file bar proportional to session tokens."""
    if not file_tokens:
        return Panel("No token data.", title=title)

    total = sum(file_tokens.values()) or 1
    max_tok = max(file_tokens.values())
    lines = [Text(title, style="bold cyan"), Text(art.create_horizontal_rule(50), style="dim")]
    for path, tokens in sorted(file_tokens.items(), key=lambda x: -x[1]):
        pct = 100 * tokens / total
        bar_w = max(1, int(20 * tokens / max_tok))
        intensity = "green" if pct < 15 else "yellow" if pct < 25 else "red"
        bar = ("█" if art.supports_unicode() else "#") * bar_w
        name = art.truncate(path.replace("\\", "/"), 28)
        lines.append(
            Text.from_markup(
                f"{name} [{intensity}]{bar}[/] {tokens:,} ({pct:.0f}%)"
            )
        )
    return Panel(Group(*lines), border_style="cyan")


def render_re_read_heat_map(
    file_reads: dict[str, int],
    *,
    waste_estimates: dict[str, int] | None = None,
) -> RenderableType:
    """Highlight files re-read multiple times (waste)."""
    if not file_reads:
        return Panel("No re-read data.", title="Re-read Heat Map", border_style="yellow")

    waste = waste_estimates or {}
    lines = [Text("Re-read Heat Map (waste)", style="bold yellow")]
    for path, count in sorted(file_reads.items(), key=lambda x: -x[1]):
        if count < 2:
            continue
        saved = waste.get(path, (count - 1) * 500)
        lines.append(
            Text.from_markup(
                f"[red]{art.truncate(path, 32)}[/red]  reads: {count}  "
                f"[dim]waste ~{saved:,} tok[/dim]"
            )
        )
    return Panel(Group(*lines), border_style="red")


def render_category_breakdown(categories: dict[str, int]) -> RenderableType:
    """Horizontal stacked bar by token category."""
    if not categories:
        return Panel("No category data.", title="Token Categories")

    total = sum(categories.values()) or 1
    colors = {
        "system": "blue",
        "user": "cyan",
        "file_reads": "green",
        "tool_calls": "yellow",
        "reasoning": "magenta",
    }
    width = 40
    bar_parts: list[tuple[str, str]] = []
    legend: list[Text] = []
    for name, tokens in sorted(categories.items(), key=lambda x: -x[1]):
        seg = max(1, int(width * tokens / total))
        color = colors.get(name, "white")
        ch = "█" if art.supports_unicode() else "#"
        bar_parts.append((ch * seg, color))
        legend.append(Text(f"  {name}: {tokens:,} ({100 * tokens / total:.0f}%)", style=color))

    line = Text()
    for segment, color in bar_parts:
        line.append(segment, style=color)
    return Panel(Group(line, Text("Legend", style="bold"), *legend), title="Token Categories")
