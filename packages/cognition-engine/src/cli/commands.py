"""
Typer CLI commands for Cognition Engine (`cc`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from src import __version__
from src.cli import formatters, prompts
from src.cli.context import ProjectContext, find_project_root
from src.core.constants import DEFAULT_SESSION_BUDGETS, SessionType
from src.core.exceptions import CognitionEngineError, DNALoadError
from src.core.types import BudgetStatus
from src.planner.phase_generator import generate_goal_plan, generate_simple_plan

app = typer.Typer(
    name="cognition-engine",
    help=(
        "AI Development Orchestrator — Persistent memory, planning, "
        "hallucination prevention, and cost control for AI coding tools"
    ),
    no_args_is_help=True,
    epilog="Run 'cc COMMAND --help' for more information on a command.",
)

_state: dict[str, object] = {"verbose": False, "project": None}


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"cognition-engine {__version__}")
        raise typer.Exit()


def _ctx() -> ProjectContext:
    root = _state.get("project") or find_project_root()
    return ProjectContext(Path(str(root)))


def _handle_error(exc: Exception) -> None:
    if isinstance(exc, typer.Exit):
        raise exc
    if isinstance(exc, CognitionEngineError):
        suggestion = ""
        if isinstance(exc, DNALoadError):
            suggestion = "Run `cognition-engine init` in your project directory."
        formatters.print_error(exc.message, details=str(exc.details), suggestion=suggestion)
    else:
        if _state.get("verbose"):
            raise exc
        formatters.print_error(str(exc))
    raise typer.Exit(1) from exc


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    project: Optional[Path] = typer.Option(
        None, "--project", "-p", help="Project root directory"
    ),
) -> None:
    """Cognition Engine — orchestrate AI-assisted development."""
    _state["verbose"] = verbose
    _state["project"] = project
    if verbose:
        import logging

        logging.basicConfig(level=logging.DEBUG)


@app.command("init")
def cmd_init(
    project_path: Optional[Path] = typer.Argument(None, help="Project directory"),
    reinit: bool = typer.Option(False, "--reinit", help="Reinitialize existing project"),
) -> None:
    """Initialize Cognition Engine for a project."""
    try:
        root = (project_path or _ctx().root).resolve()
        if not root.is_dir():
            raise CognitionEngineError(f"Not a directory: {root}")
        ctx = ProjectContext(root)
        if ctx.is_initialized() and not reinit:
            if not prompts.confirm("Project already initialized. Reinitialize? This resets tracking.", False):
                formatters.print_info("Aborted.")
                raise typer.Exit(0)
            reinit = True
        init_result = ctx.init_project(reinit=reinit)
        dna = init_result["dna"]
        scan = init_result["scan"]
        formatters.print_success(f"Initialized project: {dna['project']['name']}")
        formatters.print_info(f"Language: {scan['language']} | Framework: {scan.get('framework', 'n/a')}")
        formatters.print_info(f"Files scanned: {scan['file_count']}")
        formatters.print_info(f"DNA: {ctx.cognition_dir / 'dna.json'}")
        formatters.print_info(
            "Next: run `cognition-engine plan` to generate a plan, or `cognition-engine start` to begin."
        )
    except Exception as e:
        _handle_error(e)


@app.command("plan")
def cmd_plan(
    goal: Optional[str] = typer.Option(None, "--goal", "-g", help="Project goal description"),
    phases: int = typer.Option(24, "--phases", help="Target number of phases"),
    force: bool = typer.Option(False, "--force", help="Regenerate existing plan"),
) -> None:
    """Generate or regenerate the master project plan."""
    try:
        ctx = _ctx()
        ctx.require_initialized()
        dna = ctx.query.refresh()
        existing = dna.get("master_plan", {}).get("phase_sequence", [])
        if existing and not force:
            formatters.print_renderable(
                formatters.format_phase_progress_map(
                    existing,
                    project_name=ctx.project_name(),
                    current_phase_index=dna["master_plan"].get("current_phase", 1),
                    overall_completion=ctx.query.calculate_project_completion(),
                )
            )
            if not prompts.confirm("Generate a new plan? This replaces the current plan.", False):
                raise typer.Exit(0)

        if not goal:
            goal = prompts.ask_text("What are you building? Describe your project in a few sentences.")

        scan = ctx.scan()
        phase_list = generate_goal_plan(goal, num_phases=phases, language=scan["language"])
        formatters.print_renderable(
            formatters.format_phase_progress_map(
                phase_list,
                project_name=ctx.project_name(),
                current_phase_index=1,
                overall_completion=0,
            )
        )
        if prompts.confirm("Save this plan?", True):
            ctx.save_plan(phase_list)
            est_sessions = max(len(phase_list) * 2, len(phase_list))
            formatters.print_success(
                f"Plan saved. {len(phase_list)} phases defined. "
                f"Estimated ~{est_sessions} sessions. Run `cognition-engine start` to begin Phase 1."
            )
    except Exception as e:
        _handle_error(e)


@app.command("start")
def cmd_start(
    task: Optional[str] = typer.Option(None, "--task", help="Task description"),
    budget: Optional[int] = typer.Option(None, "--budget", help="Token budget override"),
    phase: Optional[str] = typer.Option(None, "--phase", help="Phase ID to work on"),
    model: Optional[str] = typer.Option(None, "--model", help="Model ID"),
    preview: bool = typer.Option(False, "--preview", help="Show bootstrap only"),
) -> None:
    """Start an optimized AI coding session."""
    try:
        ctx = _ctx()
        ctx.require_initialized()
        dna = ctx.query.refresh()
        phases = dna.get("master_plan", {}).get("phase_sequence", [])
        if not phases:
            formatters.print_warning("No plan found. Run `cognition-engine plan` first.")
            raise typer.Exit(1)

        if model:
            ctx.config.update("default_model", model)

        gen = ctx.bootstrap_generator()
        if preview:
            bootstrap = gen.preview_bootstrap(task or "")
            formatters.print_renderable(formatters.format_code_block(bootstrap["context_text"], "markdown"))
            formatters.print_info(f"~{bootstrap.get('token_count', 0)} tokens")
            raise typer.Exit(0)

        bootstrap = gen.generate_and_save(task or "")
        budget_tokens = budget or bootstrap.get("recommended_budget") or ctx.config.get_token_budget("BUILD")
        sid = int(bootstrap.get("session_id") or 1)
        ctx.save_session_state(
            {
                "session_id": sid,
                "budget": budget_tokens,
                "session_type": "BUILD",
                "model": model or ctx.config.get("default_model"),
            }
        )

        phase_obj = ctx.query.get_current_phase()
        formatters.print_rule("Session ready")
        formatters.print_info(f"Phase: {bootstrap.get('phase_id')} | Sub-task: {bootstrap.get('sub_task_id')}")
        formatters.print_info(f"Budget: {budget_tokens:,} tokens | Predicted: {bootstrap.get('predicted_tokens', 0):,}")
        formatters.print_info(f"Bootstrap: {ctx.cognition_dir / 'bootstrap.md'}")
        if bootstrap.get("avoid_items_included"):
            formatters.print_info(f"Avoid items: {len(bootstrap['avoid_items_included'])}")
        port = ctx.config.get("proxy.port", 8787)
        formatters.print_info(f"API proxy: configure tools to http://127.0.0.1:{port} (when proxy enabled)")
        formatters.print_success("Session started. Shield monitoring active on validate/write.")
        ctx.precompiler().warm_up()
    except Exception as e:
        _handle_error(e)


@app.command("end")
def cmd_end(
    summary: str = typer.Option("", "--summary", "-s", help="Session summary"),
    tokens: int = typer.Option(0, "--tokens", help="Tokens consumed"),
) -> None:
    """End the current session and generate reports."""
    try:
        ctx = _ctx()
        ctx.require_initialized()
        state = ctx.load_session_state()
        if not state:
            formatters.print_warning("No active session. Nothing to end.")
            raise typer.Exit(0)

        op = ctx.active_operational_memory()
        if tokens:
            op.log_api_call("session", "aggregate", tokens // 2, tokens - tokens // 2)
        sess_summary = op.get_session_summary()
        if summary:
            sess_summary["completion_notes"] = summary

        phase = ctx.query.get_current_phase()
        phase_id = phase.get("id", "PHASE_01") if phase else "PHASE_01"
        op.flush_to_dna(ctx.mutator, ctx.query, phase_id)

        ctx.session_store().close_session(int(state["session_id"]), sess_summary)
        predictor = ctx.bootstrap_generator().budget_predictor
        predictor.calibrate("BUILD", phase_id, sess_summary["tokens"]["total"], session_id=int(state["session_id"]))

        formatters.print_renderable(formatters.format_session_summary(sess_summary))

        new_insights = ctx.knowledge_synthesizer().synthesize(sess_summary)
        rl = ctx.rl_allocator()
        rl.record_session_result(
            state.get("session_type", "BUILD"),
            "MEDIUM",
            rl.get_recommended_allocation(state.get("session_type", "BUILD")),
            float(sess_summary.get("efficiency_score", 50)),
            outcome=sess_summary,
        )

        insights = new_insights or ctx.query.get_unapplied_insights()
        if insights:
            formatters.print_rule("Insights")
            for ins in insights[:5]:
                formatters.print_renderable(formatters.format_insight(ins))
        from src.navigator.recommendation_engine import RecommendationEngine
        from src.navigator.complexity_forecaster import ComplexityForecaster
        from src.navigator.debt_detector import DebtDetector
        from src.navigator.dependency_resolver import DependencyResolver
        from src.navigator.phase_tracker import PhaseTracker

        rec_engine = RecommendationEngine(
            PhaseTracker(ctx.query, ctx.mutator),
            DependencyResolver(ctx.query),
            ComplexityForecaster(ctx.query, ctx.root),
            DebtDetector(ctx.query, ctx.root),
            ctx.query,
        )
        formatters.print_info(f"Next: {rec_engine.get_next_session_prompt()}")

        ctx.clear_session_state()
        formatters.print_success(
            "Session ended. Run `cognition-engine start` for your next session."
        )
    except Exception as e:
        _handle_error(e)


@app.command("status")
def cmd_status(
    detailed: bool = typer.Option(False, "--detailed", help="Full progress map"),
    phase: Optional[str] = typer.Option(None, "--phase", help="Phase ID detail view"),
) -> None:
    """Show current project status."""
    try:
        ctx = _ctx()
        ctx.require_initialized()
        dna = ctx.query.refresh()
        phases = dna.get("master_plan", {}).get("phase_sequence", [])
        current_idx = dna.get("master_plan", {}).get("current_phase", 1)
        completion = ctx.query.calculate_project_completion()

        if phase:
            p = ctx.query.get_phase_by_id(phase)
            if not p:
                raise CognitionEngineError(f"Unknown phase {phase}")
            formatters.print_renderable(formatters.format_phase_detail(p))
            raise typer.Exit(0)

        current = ctx.query.get_current_phase()
        label = f"{current.get('id')}: {current.get('name')}" if current else ""
        formatters.print_renderable(
            formatters.format_compact_progress(phases, current_index=current_idx, overall_completion=completion, current_label=label)
        )

        if detailed:
            formatters.print_renderable(
                formatters.format_phase_progress_map(
                    phases,
                    project_name=ctx.project_name(),
                    current_phase_index=current_idx,
                    overall_completion=completion,
                    total_tokens=dna.get("project", {}).get("total_tokens_consumed", 0),
                )
            )
            recent = ctx.session_store().get_recent_sessions(3)
            if recent:
                rows = [
                    [r.get("session_id"), r.get("started_at", "")[:19], r.get("phase_id"), r.get("tokens_consumed", 0)]
                    for r in recent
                ]
                formatters.print_renderable(formatters.format_table(
                    ["ID", "Started", "Phase", "Tokens"], rows
                ))
        else:
            proj = dna.get("project", {})
            formatters.print_info(
                f"Tokens total: {proj.get('total_tokens_consumed', 0):,} | "
                f"Sessions: {proj.get('total_sessions', 0)}"
            )
    except Exception as e:
        _handle_error(e)


@app.command("budget")
def cmd_budget(
    set_budget: Optional[int] = typer.Option(None, "--set", help="Set budget limit in tokens"),
    show: bool = typer.Option(False, "--show", help="Detailed budget view"),
) -> None:
    """View or set the token budget."""
    try:
        ctx = _ctx()
        ctx.require_initialized()
        state = ctx.load_session_state() or {}
        if set_budget is not None:
            recommended = DEFAULT_SESSION_BUDGETS[SessionType.BUILD]
            if set_budget < recommended * 0.5 and not prompts.confirm(
                f"Budget {set_budget:,} is below half the recommended {recommended:,}. Continue?", False
            ):
                raise typer.Exit(0)
            state["budget"] = set_budget
            ctx.save_session_state(state)
            formatters.print_success(f"Budget set to {set_budget:,} tokens")
            return

        op = ctx.active_operational_memory()
        used = op.get_realtime_stats()["tokens_used"]
        total = int(state.get("budget", ctx.config.get_token_budget("BUILD")))
        ratio = used / total if total else 0
        from src.core.constants import budget_zone_for_ratio

        zone = budget_zone_for_ratio(ratio)
        status = BudgetStatus(
            tokens_used=used,
            tokens_remaining=max(0, total - used),
            percentage_used=round(ratio * 100, 2),
            current_zone=zone.value,
            estimated_cost=round(used * 0.000003, 4),
            session_duration_seconds=op.get_realtime_stats()["elapsed_seconds"],
            burn_rate_per_minute=0.0,
            projected_exhaustion_time=None,
        )
        formatters.print_renderable(formatters.format_budget_status(status))
    except Exception as e:
        _handle_error(e)


@app.command("insights")
def cmd_insights() -> None:
    """Show generated insights and recommendations."""
    try:
        ctx = _ctx()
        ctx.require_initialized()
        insights = ctx.query.get_unapplied_insights()
        if not insights:
            formatters.print_info("No pending insights.")
            raise typer.Exit(0)
        for ins in insights:
            formatters.print_renderable(formatters.format_insight(ins))
        recs = ctx.query.refresh().get("recommendations", [])
        applied = sum(1 for i in ctx.query.refresh().get("insights", []) if i.get("applied"))
        total = len(ctx.query.refresh().get("insights", []))
        formatters.print_info(f"Insights: {total} total, {applied} applied, {len(insights)} pending")
    except Exception as e:
        _handle_error(e)


@app.command("history")
def cmd_history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of sessions"),
    phase: Optional[str] = typer.Option(None, "--phase", help="Filter by phase"),
) -> None:
    """Show session history."""
    try:
        ctx = _ctx()
        ctx.require_initialized()
        store = ctx.session_store()
        entries = store.get_sessions_for_phase(phase) if phase else store.get_recent_sessions(limit)
        if not entries:
            formatters.print_info("No sessions found.")
            raise typer.Exit(0)
        rows = []
        for e in entries[:limit]:
            rows.append([
                e.get("session_id"),
                (e.get("started_at") or "")[:19],
                e.get("phase_id"),
                e.get("tokens_consumed", 0),
                f"{e.get('efficiency_score', 0):.0f}",
            ])
        formatters.print_renderable(
            formatters.format_table(["ID", "Started", "Phase", "Tokens", "Efficiency"], rows)
        )
    except Exception as e:
        _handle_error(e)


@app.command("config")
def cmd_config(
    key: Optional[str] = typer.Option(None, "--key", help="Configuration key"),
    value: Optional[str] = typer.Option(None, "--value", help="New value"),
    list_all: bool = typer.Option(False, "--list", help="List all configuration"),
) -> None:
    """View or edit configuration."""
    try:
        ctx = _ctx()
        data = ctx.config.data
        if list_all or (not key and not value):
            rows = [[k, _mask(k, str(v))] for k, v in _flatten_config(data).items()]
            formatters.print_renderable(formatters.format_table(["Key", "Value"], sorted(rows)))
            raise typer.Exit(0)
        if key and value is not None:
            ctx.config.update(key, _parse_value(value))
            formatters.print_success(f"Set {key} = {value}")
            raise typer.Exit(0)
        if key:
            val = ctx.config.get(key)
            formatters.print_info(f"{key} = {_mask(key, val)}")
    except Exception as e:
        _handle_error(e)


@app.command("validate")
def cmd_validate(
    file: Path = typer.Argument(..., help="File to validate"),
    code: Optional[str] = typer.Option(None, "--code", help="Code string instead of file"),
) -> None:
    """Validate AI-generated code with the Hallucination Shield."""
    try:
        ctx = _ctx()
        ctx.require_initialized()
        path = file
        original = path.read_text(encoding="utf-8") if path.is_file() and not code else ""
        proposed = code or path.read_text(encoding="utf-8")
        pipeline = ctx.validation_pipeline()
        result = pipeline.validate_code_change(str(path), original, proposed)
        verdict = result.get("final_verdict", "PASS")
        style = {"PASS": "green", "WARN": "yellow", "BLOCK": "red"}.get(verdict, "white")
        formatters.print_info(f"Verdict: [{style}]{verdict}[/{style}] ({result.get('total_time_ms', 0):.1f} ms)")
        for stage in result.get("stage_results", []):
            for err in stage.get("errors", []):
                formatters.print_error(err.get("description", ""), suggestion=err.get("suggestion", ""))
            for warn in stage.get("warnings", []):
                formatters.print_warning(warn.get("description", ""))
        if result.get("corrected_code") and verdict == "WARN":
            formatters.print_renderable(formatters.format_code_block(result["corrected_code"]))
            if prompts.confirm("Apply corrected code?", False):
                path.write_text(result["corrected_code"], encoding="utf-8")
                formatters.print_success("Applied corrections.")
        if verdict == "BLOCK":
            raise typer.Exit(1)
    except Exception as e:
        _handle_error(e)


@app.command("models")
def cmd_models(
    list_all: bool = typer.Option(False, "--list", help="List all models"),
    status: bool = typer.Option(False, "--status", help="Show availability status"),
    route: bool = typer.Option(False, "--route", help="Show routing decision for BUILD/MEDIUM"),
) -> None:
    """List models, health status, or sample routing."""
    try:
        reg = _ctx().model_registry()
        fb = __import__("src.models.fallback_manager", fromlist=["FallbackManager"]).FallbackManager(reg)
        if list_all or (not status and not route):
            rows = []
            for mid in reg.list_models():
                m = reg.get_model(mid) or {}
                p = m.get("pricing") or {}
                rows.append(
                    [
                        mid,
                        m.get("provider", ""),
                        m.get("tier", ""),
                        f"${float(p.get('input_per_1k', 0)):.4f}",
                    ]
                )
            formatters.print_renderable(formatters.format_table(["ID", "Provider", "Tier", "In/1k"], rows))
        if status:
            st = fb.get_status()
            for mid, s in sorted(st.items()):
                formatters.print_info(f"{mid}: {s}")
        if route:
            router = _ctx().intelligent_router()
            result = router.route_task(task_complexity="MEDIUM", budget_zone="green")
            formatters.print_success(router.explain_routing(result))
    except Exception as e:
        _handle_error(e)


completion_app = typer.Typer(help="Shell completion")


@completion_app.command("install")
def cmd_completion_install(
    shell: Optional[str] = typer.Option(None, "--shell", help="bash|zsh|fish"),
) -> None:
    """Install shell tab completion."""
    from src.cli.completions import install_completions

    install_completions(shell)


app.add_typer(completion_app, name="completion")


def _flatten_config(data: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in data.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten_config(v, key))
        else:
            out[key] = v
    return out


def _mask(key: str, value: object) -> str:
    if "key" in key.lower() or "secret" in key.lower():
        return "********"
    return str(value)


def _parse_value(raw: str) -> object:
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw
