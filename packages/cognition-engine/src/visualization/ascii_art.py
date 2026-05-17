"""
Terminal visual primitives for Cognition Engine (Rich + custom rendering).
"""

from __future__ import annotations

import re
import sys
from typing import Any, Literal

from rich import box as rich_box
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

BorderStyle = Literal["single", "double", "rounded", "heavy", "dashed"]
ProgressStyle = Literal["block", "shaded", "braille", "minimal", "dots"]
ArrowStyle = Literal["simple", "bold", "double", "dashed", "unicode"]
RuleStyle = Literal["solid", "dashed", "double"]

_BORDER_CHARS: dict[BorderStyle, tuple[str, str, str, str, str, str]] = {
    "single": ("┌", "┐", "└", "┘", "─", "│"),
    "double": ("╔", "╗", "╚", "╝", "═", "║"),
    "rounded": ("╭", "╮", "╰", "╯", "─", "│"),
    "heavy": ("┏", "┓", "┗", "┛", "━", "┃"),
    "dashed": ("┌", "┐", "└", "┘", "╌", "┆"),
}

_ASCII_BORDER: dict[BorderStyle, tuple[str, str, str, str, str, str]] = {
    "single": ("+", "+", "+", "+", "-", "|"),
    "double": ("+", "+", "+", "+", "=", "|"),
    "rounded": ("+", "+", "+", "+", "-", "|"),
    "heavy": ("+", "+", "+", "+", "=", "|"),
    "dashed": ("+", "+", "+", "+", "-", "|"),
}

_PROGRESS_CHARS: dict[ProgressStyle, tuple[str, str]] = {
    "block": ("█", "░"),
    "shaded": ("▓", "▒"),
    "braille": ("⣿", "⣀"),
    "minimal": ("=", "-"),
    "dots": ("●", "○"),
}

_ARROW: dict[ArrowStyle, str] = {
    "simple": "→",
    "bold": "▶",
    "double": "⇒",
    "dashed": "--->",
    "unicode": "➤",
}

_SPARK = "▁▂▃▄▅▆▇█"


def supports_unicode() -> bool:
    enc = (getattr(sys.stdout, "encoding", None) or "utf-8").lower()
    try:
        "█".encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def _border(style: BorderStyle) -> tuple[str, str, str, str, str, str]:
    table = _BORDER_CHARS if supports_unicode() else _ASCII_BORDER
    return table[style]


def create_box(
    content: str,
    *,
    title: str = "",
    border_style: BorderStyle = "rounded",
    padding: int = 1,
    width: int | None = None,
) -> str:
    """Render text inside a bordered box."""
    tl, tr, bl, br, h, v = _border(border_style)
    lines = content.splitlines() or [""]
    inner_w = max(len(line) for line in lines)
    if width:
        inner_w = max(inner_w, width - 4)
    pad = " " * padding
    body_w = inner_w + padding * 2
    top = f"{tl}{h * (body_w + 2)}{tr}"
    if title:
        title_line = f"{v} {truncate(title, body_w)} {v}"
        top = f"{tl}{h * (body_w + 2)}{tr}\n{title_line}\n{v}{h * (body_w + 2)}{v}"
    out = [top]
    for line in lines:
        padded = pad + truncate(line, inner_w).ljust(inner_w) + pad
        out.append(f"{v} {padded} {v}")
    out.append(f"{bl}{h * (body_w + 2)}{br}")
    return "\n".join(out)


def create_progress_bar(
    percent: float,
    *,
    width: int = 24,
    style: ProgressStyle = "block",
    label_inside: bool = False,
    show_percent: bool = True,
    animated: bool = False,
) -> Text:
    """Progress bar with color thresholds and optional animation marker."""
    pct = max(0.0, min(100.0, percent))
    filled, empty = _PROGRESS_CHARS.get(style, _PROGRESS_CHARS["block"])
    if not supports_unicode():
        filled, empty = "#", "."
    n = int(width * pct / 100)
    bar_chars = filled * n + empty * (width - n)
    if animated and 0 < pct < 100:
        bar_chars = bar_chars[:-1] + ("~" if not supports_unicode() else "◐")
    color = "green" if pct >= 75 else "yellow" if pct >= 50 else "red"
    label = f" {pct:.0f}%" if show_percent else ""
    if label_inside and width >= 8:
        inner = f"{pct:.0f}%".center(width)
        text = Text(inner, style=color)
    else:
        text = Text(bar_chars, style=color)
        if label:
            text.append(label, style="dim")
    return text


def create_tree(
    root_label: str,
    children: list[dict[str, Any]],
    *,
    branch_style: str = "unicode",
) -> Tree:
    """Hierarchical tree with optional icon/color per node."""
    tree = Tree(root_label)
    for node in children:
        label = node.get("label", "")
        icon = node.get("icon", "")
        style = node.get("style", "")
        line = f"{icon} {label}".strip() if icon else label
        branch = tree.add(f"[{style}]{line}[/{style}]" if style else line)
        for sub in node.get("children", []):
            sub_line = sub.get("label", "")
            branch.add(sub_line)
    return tree


def create_table(
    headers: list[str],
    rows: list[list[Any]],
    *,
    title: str = "",
    sort_column: int | None = None,
) -> Table:
    """Rich table with Cognition Engine styling."""
    t = Table(
        title=title,
        box=rich_box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
        expand=True,
    )
    for h in headers:
        t.add_column(h)
    display_rows = list(rows)
    if sort_column is not None and display_rows:
        display_rows = sorted(display_rows, key=lambda r: str(r[sort_column]))
        t.caption = f"Sorted by {headers[sort_column]}"
    for row in display_rows:
        t.add_row(*[str(c) for c in row])
    return t


def create_arrow(style: ArrowStyle = "simple") -> str:
    if not supports_unicode() and style in ("bold", "double", "unicode"):
        return "->"
    return _ARROW.get(style, "->")


def create_header(text: str, *, underline: bool = True, icon: str = "") -> Text:
    prefix = f"{icon} " if icon else ""
    header = Text(f"{prefix}{text}", style="bold cyan")
    if underline:
        header.append("\n" + ("─" * min(len(text) + len(prefix), 60)), style="dim")
    return header


def create_badge(label: str, color: str = "white") -> Text:
    return Text(f" {label} ", style=f"bold {color} on black")


def create_sparkline(values: list[float], width: int = 10) -> str:
    if not values:
        return ""
    w = max(1, width)
    if len(values) > w:
        step = len(values) / w
        sampled = [values[int(i * step)] for i in range(w)]
    else:
        sampled = values
    lo, hi = min(sampled), max(sampled)
    if hi == lo:
        return _SPARK[0] * len(sampled) if supports_unicode() else "." * len(sampled)
    chars = _SPARK if supports_unicode() else "._-=#"
    out = []
    for v in sampled:
        idx = int((v - lo) / (hi - lo) * (len(chars) - 1))
        out.append(chars[idx])
    return "".join(out)


def create_horizontal_rule(
    width: int | None = None,
    style: RuleStyle = "solid",
) -> str:
    w = width or (console_width() - 2)
    w = max(10, w)
    if style == "double":
        ch = "═" if supports_unicode() else "="
    elif style == "dashed":
        ch = "╌" if supports_unicode() else "-"
    else:
        ch = "─" if supports_unicode() else "-"
    return ch * w


def colorize(text: str, color: str = "white", *, bold: bool = False) -> Text:
    style = f"bold {color}" if bold else color
    return Text(text, style=style)


def truncate(text: str, width: int, *, word_boundary: bool = True) -> str:
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    cut = width - 1
    if word_boundary:
        space = text.rfind(" ", 0, cut)
        if space > cut // 2:
            cut = space
    return text[:cut].rstrip() + "…"


def console_width(default: int = 80) -> int:
    try:
        return Console().size.width or default
    except Exception:
        return default


def render_panel(renderable: RenderableType, title: str = "") -> Panel:
    return Panel(renderable, title=title, border_style="cyan")
