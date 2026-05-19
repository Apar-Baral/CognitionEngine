"""Format master plan and progress for the Textual REPL."""

from __future__ import annotations

from typing import Any

from src.core.constants import PhaseStatus


def format_plan_markup(
    phases: list[dict[str, Any]],
    *,
    goal: str = "",
    overall_completion: float = 0.0,
    project_name: str = "Project",
) -> str:
    """Rich markup plan block for in-terminal display."""
    lines: list[str] = [
        f"[bold #3fb950]MASTER PLAN[/] — {project_name}",
        f"[dim]{len(phases)} phases · implementation {overall_completion:.0f}% complete[/]",
    ]
    if goal.strip():
        g = goal.strip()
        preview = g if len(g) <= 200 else g[:197] + "…"
        lines.append(f"[dim]Goal:[/] {preview}")
    lines.append("")

    current_idx = 1
    for i, phase in enumerate(phases, 1):
        if phase.get("status") == PhaseStatus.IN_PROGRESS.value:
            current_idx = i
            break

    for i, phase in enumerate(phases, 1):
        pid = phase.get("id", f"PHASE_{i:02d}")
        name = phase.get("name", "")
        status = phase.get("status", PhaseStatus.NOT_STARTED.value)
        score = int(_phase_progress(phase))
        icon = _status_glyph(status)
        here = " [bold yellow]◀ current[/]" if i == current_idx else ""
        lines.append(
            f"{icon} [bold cyan]{pid}[/] [white]{name}[/] "
            f"[dim]({status}, {score}%)[/]{here}"
        )
        desc = (phase.get("description") or "")[:100]
        if desc:
            lines.append(f"   [dim]{desc}[/]")
        deliverables = [str(d) for d in phase.get("deliverables", []) if str(d).strip()]
        if deliverables:
            lines.append(f"   [dim]deliverable:[/] {deliverables[0][:110]}")
        for st in phase.get("sub_tasks", [])[:2]:
            sid = st.get("id", "")
            st_name = st.get("name", "")
            prog = st.get("progress", 0)
            crit = str(st.get("completion_criteria", "") or "")
            suffix = f" [dim]=> {crit[:70]}[/]" if crit else ""
            lines.append(f"   [dim]· {sid}[/] {st_name} [dim]{prog}%[/]{suffix}")
    lines.append("")
    lines.append("[dim]Tip: /status for tracker · Start session to refresh bootstrap[/]")
    return "\n".join(lines)


def format_plan_plain(
    phases: list[dict[str, Any]],
    *,
    goal: str = "",
    overall_completion: float = 0.0,
    project_name: str = "Project",
) -> str:
    """Plain-text plan (always visible in RichLog)."""
    lines = [
        f"MASTER PLAN — {project_name}",
        f"{len(phases)} phases · {overall_completion:.0f}% implementation complete",
    ]
    if goal.strip():
        lines.append(f"Goal: {goal.strip()[:300]}")
    lines.append("")
    for i, phase in enumerate(phases, 1):
        pid = phase.get("id", f"PHASE_{i:02d}")
        name = phase.get("name", "")
        status = phase.get("status", "?")
        score = int(_phase_progress(phase))
        mark = " <-- current" if status == PhaseStatus.IN_PROGRESS.value else ""
        lines.append(f"  {pid}  {name}  ({status}, {score}%){mark}")
        desc = (phase.get("description") or "")[:90]
        if desc:
            lines.append(f"      {desc}")
    return "\n".join(lines)


def format_shield_detail(ctx: Any) -> str:
    """How hallucination shield works in this project."""
    from src.cli.context import ProjectContext

    if not isinstance(ctx, ProjectContext):
        return "Shield: project not loaded"
    sens = ctx.config.get("shield_sensitivity", "medium")
    hall = 0
    if ctx.is_initialized():
        hall = int(ctx.query.refresh().get("project", {}).get("total_hallucinations_caught", 0))
    return (
        "[bold #f85149]Hallucination Shield[/] (core CE feature)\n\n"
        "[bold]What it checks[/]\n"
        "  · Invented Python imports (modules that do not exist)\n"
        "  · Invented APIs / functions / wrong parameters\n"
        "  · Static analysis vs project truth database\n\n"
        "[bold]When it runs[/]\n"
        "  · Agent [bold]write_file[/] on .py files (blocks bad code)\n"
        "  · CLI: [bold]cognition-engine validate[/] <file>\n"
        "  · Session [bold]/end[/] — logs caught issues to DNA\n\n"
        f"[bold]Your project[/]  sensitivity=[cyan]{sens}[/]  "
        f"total caught in DNA=[yellow]{hall}[/]\n\n"
        "[dim]Not every chat line is scanned — shield targets code changes.[/]\n"
        "[dim]Index codebase once: cognition-engine index[/]"
    )


def format_status_detail(ctx: Any) -> str:
    """Detailed progress + shield summary for /status and sidebar refresh."""
    from src.cli.context import ProjectContext

    if not isinstance(ctx, ProjectContext):
        return "No project context"
    if not ctx.is_initialized():
        return "Project not initialized"

    dna = ctx.query.refresh()
    phases = dna.get("master_plan", {}).get("phase_sequence", [])
    if not phases:
        return "No plan yet — click [bold]Generate plan[/] or /plan"

    overall = ctx.query.calculate_project_completion()
    completed = sum(1 for p in phases if p.get("status") == PhaseStatus.COMPLETED.value)
    in_prog = sum(1 for p in phases if p.get("status") == PhaseStatus.IN_PROGRESS.value)
    milestone_pct = (completed / len(phases) * 100.0) if phases else 0.0
    phase = ctx.query.get_current_phase()
    pid = phase.get("id", "—") if phase else "—"
    pname = phase.get("name", "") if phase else ""
    proj = dna.get("project", {})
    hall = int(proj.get("total_hallucinations_caught", 0))
    sens = ctx.config.get("shield_sensitivity", "medium")

    lines = [
        f"[bold]Progress[/]  implementation [cyan]{overall:.0f}%[/] · "
        f"milestones [cyan]{completed}/{len(phases)}[/] ([cyan]{milestone_pct:.0f}%[/])",
        f"[bold]Active[/]     {pid} — {pname} ({in_prog} phase(s) in progress)",
        f"[bold]Shield[/]    Hallucination detection [green]ON[/] "
        f"([dim]{sens}[/]) · caught [yellow]{hall}[/] in DNA",
        "[dim]Shield runs on Python writes (agent tools) and `cognition-engine validate`[/]",
    ]
    return "\n".join(lines)


def _status_glyph(status: str) -> str:
    if status == PhaseStatus.COMPLETED.value:
        return "[green]✓[/]"
    if status == PhaseStatus.IN_PROGRESS.value:
        return "[yellow]◎[/]"
    if status == PhaseStatus.BLOCKED.value:
        return "[red]✗[/]"
    return "[dim]○[/]"


def _phase_progress(phase: dict[str, Any]) -> float:
    subs = [st for st in phase.get("sub_tasks", []) if isinstance(st, dict)]
    if not subs:
        return float(phase.get("completion_score", 0) or 0)
    total = sum(max(int(st.get("estimated_tokens", 1) or 1), 1) for st in subs)
    if total <= 0:
        return float(phase.get("completion_score", 0) or 0)
    done = sum(
        (float(st.get("progress", 0) or 0) / 100.0)
        * max(int(st.get("estimated_tokens", 1) or 1), 1)
        for st in subs
    )
    return round(done * 100.0 / total, 2)
