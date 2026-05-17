"""
Project timeline and Gantt-style visualizations.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from src.core.constants import PhaseStatus
from src.visualization import ascii_art as art


def render_gantt_chart(
    phases: list[dict[str, Any]],
    *,
    critical_path: list[str] | None = None,
    today: date | None = None,
) -> RenderableType:
    """Gantt chart with today marker and critical path highlight."""
    if not phases:
        return Panel("No phases to chart.", title="Gantt Chart")

    today = today or date.today()
    starts: list[date] = []
    ends: list[date] = []
    for p in phases:
        s = _parse_date(p.get("started"))
        e = _parse_date(p.get("completed")) or (s + timedelta(days=7) if s else today + timedelta(days=7))
        if not s:
            s = today
        starts.append(s)
        ends.append(e)

    min_d = min(starts)
    max_d = max(ends)
    span = max((max_d - min_d).days, 1)
    crit = set(critical_path or [])
    lines = [Text(f"Timeline {min_d} → {max_d}", style="bold cyan")]

    for p, s, e in zip(phases, starts, ends):
        pid = p.get("id", "")
        offset = int(30 * (s - min_d).days / span)
        length = max(1, int(30 * max((e - s).days, 1) / span))
        status = p.get("status", PhaseStatus.NOT_STARTED.value)
        if status == PhaseStatus.COMPLETED.value:
            fill, style = "█", "green"
        elif status == PhaseStatus.IN_PROGRESS.value:
            fill, style = "█", "yellow"
        else:
            fill, style = "░", "dim"
        if not art.supports_unicode():
            fill = "#" if fill == "█" else "."
        bar = " " * offset + fill * length
        if pid in crit:
            style = "bold " + style
        today_col = int(30 * (today - min_d).days / span)
        marker = list(bar.ljust(35))
        if 0 <= today_col < len(marker):
            marker[today_col] = "|"
        lines.append(Text(f"{pid} {''.join(marker)}", style=style))

    lines.append(Text(f"Today: {today}", style="bold yellow"))
    return Panel(Group(*lines), title="Gantt Chart", border_style="blue")


def render_milestone_timeline(
    phases: list[dict[str, Any]],
    *,
    every: int = 5,
) -> RenderableType:
    """Executive milestone timeline."""
    lines = []
    for i, p in enumerate(phases):
        if (i + 1) % every != 0 and i != len(phases) - 1:
            continue
        when = p.get("completed") or p.get("started") or "planned"
        mark = "✓" if p.get("status") == PhaseStatus.COMPLETED.value else "○"
        if not art.supports_unicode():
            mark = "+" if mark == "✓" else "o"
        lines.append(Text(f"{when}  {mark}  {p.get('id')} — {p.get('name', '')}"))
    return Panel(Group(*lines), title="Milestone Timeline")


def render_session_calendar(sessions: list[dict[str, Any]]) -> RenderableType:
    """Calendar of sessions colored by efficiency."""
    if not sessions:
        return Panel("No sessions recorded.", title="Session Calendar")

    lines = []
    for s in sorted(sessions, key=lambda x: x.get("date", ""), reverse=True)[:14]:
        eff = float(s.get("efficiency_score", 0.5))
        color = "green" if eff >= 0.75 else "yellow" if eff >= 0.5 else "red"
        lines.append(
            Text.from_markup(
                f"[{color}]■[/] {s.get('date', '')}  "
                f"#{s.get('session_id', '?')}  {s.get('phase_id', '')}  "
                f"eff {eff:.2f}  {s.get('tokens', 0):,} tok"
            )
        )
    return Panel(Group(*lines), title="Session Calendar", border_style="cyan")


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except ValueError:
        return None
