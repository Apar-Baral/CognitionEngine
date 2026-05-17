"""
Phase progress visualizations for terminal output.
"""

from __future__ import annotations

from typing import Any

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from src.core.constants import PhaseStatus, TaskStatus
from src.visualization import ascii_art as art

_STATUS_ICON: dict[str, tuple[str, str]] = {
    PhaseStatus.COMPLETED.value: ("✅", "green"),
    PhaseStatus.IN_PROGRESS.value: ("🔄", "bold yellow"),
    PhaseStatus.IN_REVIEW.value: ("👁️", "cyan"),
    PhaseStatus.BLOCKED.value: ("🔒", "red"),
    PhaseStatus.NOT_STARTED.value: ("⬜", "dim"),
    PhaseStatus.CANCELLED.value: ("✘", "red"),
}

_ASCII_STATUS = {
    PhaseStatus.COMPLETED.value: ("[+]", "green"),
    PhaseStatus.IN_PROGRESS.value: ("[~]", "bold yellow"),
    PhaseStatus.IN_REVIEW.value: ("[?]", "cyan"),
    PhaseStatus.BLOCKED.value: ("[!]", "red"),
    PhaseStatus.NOT_STARTED.value: ("[ ]", "dim"),
    PhaseStatus.CANCELLED.value: ("[x]", "red"),
}


def _icon(status: str) -> tuple[str, str]:
    table = _STATUS_ICON if art.supports_unicode() else _ASCII_STATUS
    return table.get(status, ("•", "white"))


def render_phase_progress_map(
    phases: list[dict[str, Any]],
    *,
    project_name: str = "Project",
    project_version: str = "0.1.0",
    current_phase_index: int = 1,
    overall_completion: float = 0.0,
    total_sessions: int = 0,
    total_tokens: int = 0,
    completion_trend: list[float] | None = None,
) -> RenderableType:
    """Full project progress map with header, phase rows, and footer."""
    trend = completion_trend or []
    spark = art.create_sparkline(trend, 10) if trend else ""
    header_lines = [
        Text.from_markup(f"[bold]{project_name}[/bold] v{project_version}"),
        art.create_progress_bar(overall_completion, width=40, style="block"),
        Text(
            f"Phases: {len(phases)} | Done: {_count(phases, PhaseStatus.COMPLETED)} | "
            f"Active: {_count(phases, PhaseStatus.IN_PROGRESS)} | "
            f"Sessions: {total_sessions} | Tokens: {total_tokens:,}",
            style="dim",
        ),
    ]
    if spark:
        header_lines.append(Text(f"Trend: {spark}", style="dim cyan"))

    rows: list[RenderableType] = []
    for i, phase in enumerate(phases):
        rows.append(_phase_row(phase, i, current_phase_index))

    footer = Text(
        f"Summary: {len(phases)} phases | {_count(phases, PhaseStatus.COMPLETED)} complete | "
        f"{overall_completion:.0f}% overall",
        style="dim",
    )
    return Panel(
        Group(*header_lines, Text(""), *rows, Text(""), footer),
        title=f"Progress Map — {overall_completion:.0f}%",
        border_style="cyan",
    )


def _phase_row(phase: dict[str, Any], index: int, current_index: int) -> RenderableType:
    status = phase.get("status", PhaseStatus.NOT_STARTED.value)
    icon, style = _icon(status)
    pid = phase.get("id", "")
    name = art.truncate(phase.get("name", ""), 28)
    pct = float(phase.get("completion_score", 0))
    bar = art.create_progress_bar(pct, width=20, style="block")

    line = Text()
    line.append(f"{icon} ", style=style)
    line.append(f"{pid} ", style=f"bold {style}")
    line.append(f"{name} ")
    line.append(bar)
    if status == PhaseStatus.COMPLETED.value:
        done = phase.get("completed", "")
        sessions = phase.get("sessions_used", 0)
        line.append(f"  [dim]{done} ({sessions} sessions)[/dim]")
    elif index == current_index - 1 or status == PhaseStatus.IN_PROGRESS.value:
        line.append("  [bold yellow]◄── YOU ARE HERE[/bold yellow]")
    elif status == PhaseStatus.BLOCKED.value:
        reason = phase.get("blocked_by", [])
        note = ", ".join(reason) if reason else "dependency incomplete"
        line.append(f"  [dim red]{note}[/dim red]")

    extras: list[RenderableType] = [line]
    if status == PhaseStatus.IN_PROGRESS.value:
        for st in phase.get("sub_tasks", []):
            if st.get("status") == TaskStatus.IN_PROGRESS.value:
                mini = art.create_progress_bar(float(st.get("progress", 0)), width=12)
                sub = Text(f"    └ {st.get('id', '')}: {art.truncate(st.get('name', ''), 24)} ")
                sub.append(mini)
                extras.append(sub)
                break
    return Group(*extras)


def render_compact_progress(
    phases: list[dict[str, Any]],
    *,
    current_index: int = 1,
    overall_completion: float = 0.0,
    max_width: int = 80,
) -> str:
    """Single-line progress for status bars."""
    icons = []
    for i, p in enumerate(phases):
        icon, _ = _icon(p.get("status", PhaseStatus.NOT_STARTED.value))
        if i == current_index - 1:
            icons.append(f"[bold yellow]{icon}[/bold yellow]")
        else:
            icons.append(icon)
    seq = "".join(icons)
    current = phases[current_index - 1] if 0 < current_index <= len(phases) else {}
    pid = current.get("id", "—")
    line = (
        f"{seq}  {overall_completion:.0f}% ({_count(phases, PhaseStatus.COMPLETED)}/{len(phases)} phases)"
        f" — {pid}"
    )
    return art.truncate(line, max_width, word_boundary=False)


def render_phase_detail(phase: dict[str, Any], *, dependents: list[str] | None = None) -> RenderableType:
    """Detailed single-phase panel."""
    status = phase.get("status", "")
    badge = art.create_badge(status.upper().replace("_", " "), _badge_color(status))
    header = Group(
        Text.from_markup(f"[bold]{phase.get('name', '')}[/bold] ({phase.get('id', '')})"),
        badge,
        Text(phase.get("description", ""), style="dim"),
        art.create_progress_bar(float(phase.get("completion_score", 0)), width=36),
    )

    sub_lines = []
    for st in phase.get("sub_tasks", []):
        st_icon, _ = _icon(
            TaskStatus.DONE.value
            if st.get("status") == TaskStatus.DONE.value
            else st.get("status", TaskStatus.PENDING.value)
        )
        bar = art.create_progress_bar(float(st.get("progress", 0)), width=10)
        agent = st.get("assigned_agent", "—")
        tokens = st.get("actual_tokens", 0)
        sub_lines.append(
            Text.assemble(
                (f"{st_icon} {st.get('id', '')} ", ""),
                (st.get("name", ""), "bold"),
                (" ", ""),
                (bar, ""),
                (f"  {agent} {tokens:,}tok", "dim"),
            )
        )

    deps = phase.get("dependencies", [])
    dep_text = Text(f"Depends on: {', '.join(deps) or 'none'}", style="dim")
    if dependents:
        dep_text.append(f"\nBlocks: {', '.join(dependents)}", style="dim yellow")

    files = []
    for st in phase.get("sub_tasks", []):
        files.extend(st.get("files_modified", []))
    file_text = Text(f"Files: {', '.join(files[:8]) or 'none'}", style="dim")

    timeline = Text(
        f"Started: {phase.get('started', '—')} | Est. tokens: {phase.get('estimated_tokens', 0):,}",
        style="dim",
    )

    return Panel(
        Group(
            header,
            Text("Sub-tasks", style="bold cyan"),
            *sub_lines or [Text("  (none)", style="dim")],
            dep_text,
            file_text,
            timeline,
        ),
        title="Phase Detail",
        border_style="blue",
    )


def render_milestone_map(phases: list[dict[str, Any]], *, every: int = 5) -> RenderableType:
    """High-level milestone view (every Nth phase)."""
    lines = []
    for i, p in enumerate(phases):
        if (i + 1) % every != 0 and i != len(phases) - 1:
            continue
        icon, style = _icon(p.get("status", PhaseStatus.NOT_STARTED.value))
        span_end = min(i + every, len(phases))
        span = f"PHASE_{i + 1:02d}–PHASE_{span_end:02d}"
        lines.append(
            Text.from_markup(
                f"{icon} [bold {style}]{p.get('id')}[/bold {style}] "
                f"{p.get('name', '')} [dim]({span})[/dim]"
            )
        )
    return Panel(Group(*lines), title="Milestone Map", border_style="cyan")


def render_blocker_report(blocked_phases: list[dict[str, Any]]) -> RenderableType:
    """Focused report on blocked phases sorted by downstream impact."""
    if not blocked_phases:
        return Panel("No blocked phases.", title="Blockers", border_style="green")

    rows = []
    for p in sorted(blocked_phases, key=lambda x: len(x.get("blocked_by", [])), reverse=True):
        reason = ", ".join(p.get("blocked_by", [])) or "unknown"
        deps = ", ".join(p.get("dependencies", [])) or "none"
        rows.append(
            Text.from_markup(
                f"[red]🔒 {p.get('id')}[/red] {p.get('name', '')}\n"
                f"  [dim]Blocked by:[/dim] {reason}\n"
                f"  [dim]Waiting on:[/dim] {deps}"
            )
        )
    return Panel(Group(*rows), title="Blocker Report", border_style="red")


def _count(phases: list[dict[str, Any]], status: PhaseStatus) -> int:
    return sum(1 for p in phases if p.get("status") == status.value)


def _badge_color(status: str) -> str:
    return {
        PhaseStatus.COMPLETED.value: "green",
        PhaseStatus.IN_PROGRESS.value: "yellow",
        PhaseStatus.BLOCKED.value: "red",
        PhaseStatus.IN_REVIEW.value: "cyan",
    }.get(status, "white")
