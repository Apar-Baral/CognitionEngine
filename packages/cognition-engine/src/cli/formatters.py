"""
Rich formatters for Cognition Engine CLI output.
"""

from __future__ import annotations

import difflib
import sys
from datetime import timedelta
from typing import Any

from rich import box
from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.rule import Rule
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from src.core.constants import BudgetZone, PhaseStatus
from src.core.types import BudgetStatus

def _supports_unicode() -> bool:
    enc = (getattr(sys.stdout, "encoding", None) or "utf-8").lower()
    try:
        "✅".encode(enc)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


console = Console(legacy_windows=sys.platform == "win32")

ICONS = {
    PhaseStatus.COMPLETED.value: "✅",
    PhaseStatus.IN_PROGRESS.value: "🔄",
    PhaseStatus.IN_REVIEW.value: "👁️",
    PhaseStatus.BLOCKED.value: "🔒",
    PhaseStatus.NOT_STARTED.value: "⬜",
    PhaseStatus.CANCELLED.value: "✘",
}

ASCII_ICONS = {
    PhaseStatus.COMPLETED.value: "[+]",
    PhaseStatus.IN_PROGRESS.value: "[~]",
    PhaseStatus.IN_REVIEW.value: "[?]",
    PhaseStatus.BLOCKED.value: "[!]",
    PhaseStatus.NOT_STARTED.value: "[ ]",
    PhaseStatus.CANCELLED.value: "[x]",
}


def _status_icon(status: str) -> str:
    icons = ICONS if _supports_unicode() else ASCII_ICONS
    return icons.get(status, "•" if _supports_unicode() else "-")

ZONE_STYLE = {
    BudgetZone.GREEN.value: "green",
    BudgetZone.YELLOW.value: "yellow",
    BudgetZone.RED.value: "red",
    BudgetZone.WRAP_UP.value: "bold yellow",
    BudgetZone.EXHAUSTED.value: "bold red",
}


def format_phase_progress_map(
    phases: list[dict[str, Any]],
    *,
    project_name: str = "Project",
    current_phase_index: int = 0,
    overall_completion: float = 0.0,
    total_tokens: int = 0,
) -> Table:
    title = f"{project_name} — {overall_completion:.0f}% complete"
    table = Table(
        title=title,
        box=box.ROUNDED,
        header_style="bold cyan",
        show_lines=False,
        expand=True,
    )
    table.add_column("", width=3, justify="center")
    table.add_column("Phase", style="bold")
    table.add_column("Name")
    table.add_column("Progress", min_width=18)
    table.add_column("%", justify="right", width=6)
    table.add_column("Note", style="dim")

    completed = in_prog = blocked = 0
    for i, phase in enumerate(phases):
        status = phase.get("status", PhaseStatus.NOT_STARTED.value)
        icon = _status_icon(status)
        if status == PhaseStatus.COMPLETED.value:
            completed += 1
        elif status == PhaseStatus.IN_PROGRESS.value:
            in_prog += 1
        elif status == PhaseStatus.BLOCKED.value:
            blocked += 1

        pct = phase.get("completion_score", 0)
        if not pct and "completion_percentage" in phase:
            pct = int(phase["completion_percentage"])
        bar = ProgressBar(total=100, completed=min(100, int(pct)), style="cyan", complete_style="green")

        note = ""
        if i == current_phase_index - 1:
            note = Text("◄── YOU ARE HERE", style="bold yellow")
        elif status == PhaseStatus.BLOCKED.value:
            blockers = phase.get("blocked_by", [])
            note = Text("; ".join(blockers[:2]) or "blocked", style="dim red")
        elif status == PhaseStatus.COMPLETED.value and phase.get("completed"):
            note = Text(str(phase.get("completed")), style="dim")

        table.add_row(
            icon,
            phase.get("id", ""),
            (phase.get("name", "") or "")[:40],
            bar,
            str(int(pct)),
            note,
        )

    table.caption = (
        f"Phases: {len(phases)} | Done: {completed} | Active: {in_prog} | "
        f"Blocked: {blocked} | Tokens: {total_tokens:,}"
    )
    return table


def format_compact_progress(
    phases: list[dict[str, Any]],
    *,
    current_index: int = 1,
    overall_completion: float = 0.0,
    current_label: str = "",
) -> Text:
    icons = []
    for i, p in enumerate(phases):
        icon = _status_icon(p.get("status", PhaseStatus.NOT_STARTED.value))
        if i == current_index - 1:
            icons.append(f"[bold yellow]{icon}[/bold yellow]")
        else:
            icons.append(icon)
    seq = "".join(icons)
    return Text.from_markup(
        f"{seq}  {overall_completion:.0f}% ({current_index}/{len(phases)} phases)"
        + (f" — {current_label}" if current_label else "")
    )


def format_phase_detail(phase: dict[str, Any]) -> Panel:
    status = phase.get("status", "")
    style = "green" if status == PhaseStatus.COMPLETED.value else "yellow"
    lines = [
        f"[bold]{phase.get('name')}[/bold]",
        phase.get("description", ""),
        f"Status: [{style}]{status}[/{style}]",
        f"Completion: {phase.get('completion_score', 0)}%",
    ]
    subs = Table(box=None, show_header=True, header_style="bold")
    subs.add_column("ID")
    subs.add_column("Sub-task")
    subs.add_column("Status")
    subs.add_column("Progress")
    for st in phase.get("sub_tasks", []):
        if isinstance(st, dict):
            subs.add_row(
                st.get("id", ""),
                st.get("name", ""),
                st.get("status", ""),
                f"{st.get('progress', 0)}%",
            )
    body = Group(*[Text(l) for l in lines], subs)
    return Panel(body, title=phase.get("id", "Phase"), border_style="cyan")


def format_session_summary(summary: dict[str, Any]) -> Panel:
    tokens = summary.get("tokens", {})
    total = tokens.get("total", 0)
    budget_pct = summary.get("budget_adherence_percentage", 100)
    style = "green" if budget_pct >= 90 else "yellow" if budget_pct >= 70 else "red"
    stars = "⭐" * min(5, max(1, int(summary.get("efficiency_score", 50) / 20)))
    duration = summary.get("duration_seconds", 0)
    dur = str(timedelta(seconds=int(duration)))
    body = (
        f"Session #{summary.get('session_id', '?')}\n"
        f"Duration: {dur}\n"
        f"Tokens: {total:,} [{style}]{budget_pct:.0f}% budget adherence[/{style}]\n"
        f"Cost: ${summary.get('cost_incurred', 0):.4f}\n"
        f"Efficiency: {stars} ({summary.get('efficiency_score', 0)})\n"
        f"Hallucinations caught: {summary.get('hallucinations_caught', 0)}\n"
        f"Files modified: {summary.get('files_modified_count', 0)}"
    )
    return Panel(body, title="Session Summary", border_style=style)


def format_budget_status(status: BudgetStatus | dict[str, Any]) -> Panel:
    if isinstance(status, dict):
        used = status.get("tokens_used", 0)
        total = status.get("budget_tokens", 1)
        pct = status.get("percentage_used", used / total * 100 if total else 0)
        zone = status.get("current_zone", "green")
        cost = status.get("cost_so_far", status.get("cost_incurred", 0))
        burn = status.get("burn_rate_per_minute", 0)
        remaining = status.get("estimated_minutes_remaining")
    else:
        used = status.tokens_used
        total = used + status.tokens_remaining
        pct = status.percentage_used
        zone = status.current_zone
        cost = status.estimated_cost
        burn = status.burn_rate_per_minute
        remaining = None

    zstyle = ZONE_STYLE.get(zone, "white")
    bar = ProgressBar(total=total or 1, completed=used, style=zstyle, complete_style=zstyle)
    lines = [
        f"Tokens: {used:,} / {total:,} ({pct:.1f}%)",
        f"Zone: [{zstyle}]{zone.upper()}[/{zstyle}]",
        f"Cost: ${cost:.2f}",
        f"Burn rate: {burn:,.0f} tokens/min",
    ]
    if remaining is not None:
        lines.append(f"Est. remaining: {remaining:.0f} min")
    if zone in (BudgetZone.YELLOW.value, BudgetZone.RED.value, BudgetZone.WRAP_UP.value):
        lines.append("[bold yellow]⚠ Consider wrapping up this session[/bold yellow]")
    return Panel(Group(bar, *lines), title="Budget", border_style=zstyle)


def format_insight(insight: dict[str, Any]) -> Panel:
    badge = insight.get("type", "insight")
    finding = insight.get("finding", "")
    conf = insight.get("confidence", 0)
    applied = insight.get("applied", False)
    action = insight.get("actionability", "")
    body = (
        f"[bold cyan]{badge}[/bold cyan]\n{finding}\n"
        f"Confidence: {conf * 100:.0f}% | Applied: {applied}"
    )
    if action == "HIGH":
        body += "\n[bold yellow]→ Recommended action[/bold yellow]"
    return Panel(body, border_style="blue")


def format_error(message: str, *, details: str = "", suggestion: str = "") -> Panel:
    body = f"[bold]{message}[/bold]"
    if details:
        body += f"\n\n{details}"
    if suggestion:
        body += f"\n\n[dim]Suggested:[/dim] {suggestion}"
    err_title = "Error" if not _supports_unicode() else "✘ Error"
    return Panel(body, title=err_title, border_style="red")


def format_success(message: str) -> Panel:
    prefix = "OK" if not _supports_unicode() else "✔"
    return Panel(f"{prefix} {message}", border_style="green")


def format_warning(message: str) -> Panel:
    prefix = "!" if not _supports_unicode() else "⚠"
    return Panel(f"{prefix} {message}", border_style="yellow")


def format_table(headers: list[str], rows: list[list[Any]]) -> Table:
    t = Table(box=box.SIMPLE_HEAVY, header_style="bold cyan")
    for h in headers:
        t.add_column(h)
    for row in rows:
        t.add_row(*[str(c) for c in row])
    return t


def format_code_block(code: str, language: str = "python") -> Panel:
    return Panel(Syntax(code, language, theme="monokai", line_numbers=True))


def format_diff(original: str, modified: str) -> RenderableType:
    lines = difflib.unified_diff(
        original.splitlines(),
        modified.splitlines(),
        fromfile="before",
        tofile="after",
        lineterm="",
    )
    text = "\n".join(lines) or "(no changes)"
    return Syntax(text, "diff", theme="monokai")


def format_timeline(events: list[dict[str, Any]]) -> Tree:
    tree = Tree("[bold]Timeline[/bold]")
    for ev in events:
        tree.add(f"[dim]{ev.get('date', '')}[/dim] {ev.get('description', '')}")
    return tree


def format_spinner_message(message: str) -> str:
    return message


def print_renderable(renderable: RenderableType) -> None:
    console.print(renderable)


def print_success(message: str) -> None:
    console.print(format_success(message))


def print_error(message: str, **kwargs: Any) -> None:
    console.print(format_error(message, **kwargs))


def print_warning(message: str) -> None:
    console.print(format_warning(message))


def print_info(message: str) -> None:
    prefix = "i" if not _supports_unicode() else "ℹ"
    console.print(f"[cyan]{prefix}[/cyan] {message}")


def print_panel(title: str, body: str) -> None:
    console.print(Panel(body, title=title, border_style="blue"))


def print_rule(title: str = "") -> None:
    console.print(Rule(title, style="dim"))
