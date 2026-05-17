"""
Live session dashboard and end-of-session summaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from rich.columns import Columns
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.text import Text

from src.core.constants import BudgetZone
from src.core.types import BudgetStatus
from src.visualization import ascii_art as art


def render_live_dashboard(
    session_state: dict[str, Any],
    *,
    project_name: str = "Project",
    budget: BudgetStatus | None = None,
    operational: dict[str, Any] | None = None,
) -> RenderableType:
    """Real-time session dashboard (refresh every 2–5s)."""
    op = operational or {}
    bud = budget or session_state.get("budget_status")
    sid = session_state.get("session_id", 1)
    elapsed = session_state.get("elapsed_minutes", 0)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    top = Text.from_markup(
        f"[bold]Session #{sid}[/bold]  {project_name}"
        f"  [dim]│[/dim]  {elapsed:.0f} min"
        f"  [dim]│[/dim]  {now}",
        justify="center",
    )

    phase_id = session_state.get("phase_id", op.get("phase_id", "—"))
    sub_task = session_state.get("sub_task_id", op.get("sub_task_id", "—"))
    left_lines = [
        Text.from_markup(f"[bold cyan]Phase[/bold cyan] {phase_id}"),
        Text(f"Sub-task: {sub_task}", style="dim"),
    ]

    if isinstance(bud, BudgetStatus):
        zone = bud.current_zone
        pct = bud.percentage_used
        total = bud.tokens_used + bud.tokens_remaining
        tokens_line = f"{bud.tokens_used:,} / {total:,} ({pct:.0f}%)"
        bar = art.create_progress_bar(pct, width=32, style="block")
        zcolor = {"green": "green", "yellow": "yellow", "red": "red"}.get(zone, "white")
        left_lines.extend(
            [
                Text("Budget", style="bold"),
                bar,
                Text(tokens_line, style=zcolor),
                Text(f"Cost: ${bud.estimated_cost:.2f}", style="dim"),
            ]
        )
    elif isinstance(bud, dict):
        left_lines.append(art.create_progress_bar(float(bud.get("percent_used", 0)), width=32))

    eff = float(session_state.get("efficiency_score", op.get("efficiency_score", 0)))
    eff_trend = session_state.get("efficiency_trend", [])
    spark = art.create_sparkline(eff_trend, 8)
    left_lines.append(Text(f"Efficiency: {eff:.2f}  {spark}", style="cyan"))

    agents = session_state.get("agents", op.get("agents", []))
    agent_lines = [Text("Agents", style="bold cyan")]
    for ag in agents[:5]:
        agent_lines.append(
            Text(
                f"  {ag.get('type', 'agent')}: {ag.get('model', '—')} "
                f"[{ag.get('status', 'idle')}] {ag.get('tokens', 0):,} tok",
                style="dim",
            )
        )
    if not agents:
        agent_lines.append(Text("  (none active)", style="dim"))

    hall = int(session_state.get("hallucinations_caught", op.get("hallucinations_caught", 0)))
    cats = session_state.get("hallucination_categories", {})
    cat_str = ", ".join(f"{k}:{v}" for k, v in cats.items()) if cats else "—"
    files = session_state.get("files_modified", op.get("files_modified", []))
    right_lines = [
        *agent_lines,
        Text(f"Hallucinations: {hall} ({cat_str})", style="yellow" if hall else "dim"),
        Text(f"Files modified: {len(files)}", style="dim"),
    ]
    for f in files[-3:]:
        right_lines.append(Text(f"  • {art.truncate(str(f), 40)}", style="dim"))
    shield = session_state.get("shield_status", "active")
    right_lines.append(Text(f"Shield: {shield}", style="green" if shield == "active" else "dim"))

    bottom_zone = ""
    if isinstance(bud, BudgetStatus):
        eta = bud.projected_exhaustion_time or "—"
        bottom_zone = (
            f"Zone: {bud.current_zone}  Burn: {bud.burn_rate_per_minute:.0f} tok/min  ETA: {eta}"
        )
    bottom = Text(bottom_zone or "Ready", style="dim")

    main = Columns(
        [Panel(Group(*left_lines), border_style="blue"), Panel(Group(*right_lines), border_style="blue")],
        equal=True,
    )
    return Panel(Group(top, main, bottom), title="Live Dashboard", border_style="cyan")


def render_minimal_dashboard(session_state: dict[str, Any], *, max_width: int = 72) -> str:
    """Single-line dashboard for status bars."""
    phase = session_state.get("phase_id", "—")
    bud = session_state.get("budget_status")
    pct = bud.percentage_used if isinstance(bud, BudgetStatus) else float(session_state.get("budget_pct", 0))
    bar = art.create_progress_bar(pct, width=12, show_percent=False)
    eff = session_state.get("efficiency_score", 0)
    eta = ""
    if isinstance(bud, BudgetStatus) and bud.projected_exhaustion_time:
        eta = bud.projected_exhaustion_time[:8]
    line = f"{phase} | {bar} | eff {eff:.2f} | {eta}"
    return art.truncate(str(line), max_width, word_boundary=False)


def render_session_end_summary(summary: dict[str, Any]) -> RenderableType:
    """Detailed end-of-session report."""
    predicted = summary.get("predicted_tokens", 0)
    actual = summary.get("tokens_consumed", summary.get("total_tokens", 0))
    savings = summary.get("routing_savings_usd", 0)
    grade = summary.get("efficiency_grade", "B")
    explanation = summary.get("efficiency_explanation", "")
    accomplished = summary.get("accomplished", summary.get("summary", ""))
    next_action = summary.get("next_action", summary.get("resume_from", ""))

    lines = [
        Text.from_markup("[bold]Session Complete[/bold]"),
        Text(f"Predicted: {predicted:,} tokens  |  Actual: {actual:,} tokens"),
        Text(f"Model routing savings: ${savings:.2f}", style="green" if savings > 0 else "dim"),
        Text(f"Grade: {grade} — {explanation}", style="cyan"),
        Text("Hallucinations:", style="bold"),
    ]
    for h in summary.get("hallucinations", [])[:5]:
        lines.append(Text(f"  • {h.get('category', '')}: {h.get('description', '')[:60]}", style="yellow"))
    lines.extend(
        [
            Text("Accomplished:", style="bold"),
            Text(accomplished or "—", style="dim"),
            Text("Next:", style="bold green"),
            Text(next_action or "—"),
        ]
    )
    return Panel(Group(*lines), title="Session Summary", border_style="green")
