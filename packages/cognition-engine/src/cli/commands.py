"""
Typer CLI commands for Cognition Engine (`cc`).
"""

from __future__ import annotations

import json
import sys
import subprocess
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
        suggestion = ""
        if isinstance(exc, TypeError) and "not 'dict'" in str(exc):
            suggestion = (
                "Outdated cognition-engine install (missing end-session fix). "
                "Run `cognition-engine doctor`, then reinstall from GitHub commit 0ed9ed8+."
            )
        formatters.print_error(str(exc), suggestion=suggestion)
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


@app.command("setup")
def cmd_setup(
    project_path: Optional[Path] = typer.Option(
        None, "--project", "-p", help="Project directory (default: current folder)"
    ),
    full: bool = typer.Option(
        False, "--full", help="Full wizard (git, GitHub, model list). Default is quick Baral setup."
    ),
    non_interactive: bool = typer.Option(
        False, "--yes", "-y", help="Skip interactive prompts"
    ),
    git: Optional[bool] = typer.Option(
        None, "--git/--no-git", help="Initialize git for project (default: ask once)"
    ),
    semantic: bool = typer.Option(
        False,
        "--semantic",
        help="Also install Chroma/embeddings (~4GB). Default install is slim.",
    ),
    github: Optional[bool] = typer.Option(
        None,
        "--github/--no-github",
        help="Push project to GitHub after git init (default: ask)",
    ),
) -> None:
    """Quick setup (default) or full wizard with --full."""
    try:
        from src.cli.setup_wizard import run_full_setup

        target = (project_path or Path.cwd()).resolve()
        run_full_setup(
            target,
            interactive=not non_interactive,
            init_git=git,
            push_github=github,
            install_semantic=semantic,
            quick=not full,
        )
    except Exception as e:
        _handle_error(e)


@app.command("git-init")
def cmd_git_init(
    project_path: Optional[Path] = typer.Argument(None, help="Project directory"),
    no_commit: bool = typer.Option(False, "--no-commit", help="Skip initial commit"),
) -> None:
    """Initialize git with CE-friendly .gitignore."""
    try:
        from src.cli.git_helpers import git_init_project, write_project_gitignore

        root = (project_path or _ctx().root).resolve()
        write_project_gitignore(root)
        for msg in git_init_project(root, initial_commit=not no_commit):
            formatters.print_success(msg)
    except Exception as e:
        _handle_error(e)


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


@app.command("goal")
def cmd_goal(
    set_goal: Optional[str] = typer.Option(None, "--set", "-s", help="Set the full project goal"),
    show: bool = typer.Option(False, "--show", help="Print current goal"),
) -> None:
    """View or set the full project goal (shown in bootstrap and GOAL.md)."""
    try:
        ctx = _ctx()
        ctx.require_initialized()
        if set_goal:
            ctx.set_project_goal(set_goal)
            _write_goal_file(ctx, set_goal)
            formatters.print_success("Project goal updated.")
            formatters.print_info(set_goal[:500] + ("..." if len(set_goal) > 500 else ""))
            raise typer.Exit(0)
        goal = ctx.get_project_goal()
        if show or not set_goal:
            if not goal:
                formatters.print_warning(
                    "No goal set. Use: cognition-engine goal --set \"Your full goal...\" "
                    "or cognition-engine plan --goal \"...\""
                )
                raise typer.Exit(0)
            formatters.print_rule("Project goal")
            formatters.print_renderable(formatters.format_code_block(goal, "text"))
    except Exception as e:
        _handle_error(e)


@app.command("plan")
def cmd_plan(
    goal: Optional[str] = typer.Option(None, "--goal", "-g", help="Project goal description"),
    phases: int = typer.Option(24, "--phases", help="Target number of phases"),
    force: bool = typer.Option(False, "--force", help="Regenerate existing plan"),
    use_llm: bool = typer.Option(False, "--llm", help="Use LLM to tailor phase descriptions"),
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
        if use_llm:
            phase_list = _llm_enrich_plan(ctx, phase_list, goal)
        formatters.print_renderable(
            formatters.format_phase_progress_map(
                phase_list,
                project_name=ctx.project_name(),
                current_phase_index=1,
                overall_completion=0,
            )
        )
        if prompts.confirm("Save this plan?", True):
            ctx.save_plan(phase_list, goal=goal or "")
            _write_goal_file(ctx, goal or "")
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

        active_model = _apply_session_model(ctx, model)

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
                "model": active_model,
            }
        )

        phase_obj = ctx.query.get_current_phase()
        formatters.print_rule("Session ready")
        goal_preview = ctx.get_project_goal()
        if goal_preview:
            preview = goal_preview if len(goal_preview) <= 120 else goal_preview[:117] + "..."
            formatters.print_info(f"Project goal: {preview}")
        formatters.print_info(f"Model: {active_model}")
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
    no_commit: bool = typer.Option(False, "--no-commit", help="Skip auto git commit"),
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
        if summary:
            op.set_completion_notes(summary)
        sess_summary = op.get_session_summary()

        phase = ctx.query.get_current_phase()
        phase_id = phase.get("id", "PHASE_01") if phase else "PHASE_01"
        op.flush_to_dna(ctx.mutator, ctx.query, phase_id)

        ctx.session_store().close_session(int(state["session_id"]), sess_summary)
        predictor = ctx.bootstrap_generator().budget_predictor
        predictor.calibrate("BUILD", phase_id, sess_summary["tokens"]["total"], session_id=int(state["session_id"]))

        formatters.print_renderable(formatters.format_session_summary(sess_summary))

        try:
            from src.memory.vector_store import VectorMemoryStore

            VectorMemoryStore(ctx.root, ctx.project_name()).index_session_summary(sess_summary)
        except Exception:
            pass

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
        if summary and not no_commit:
            from src.cli.git_helpers import auto_commit, auto_commit_prefix, should_auto_commit

            if should_auto_commit(ctx.config):
                git_msg = auto_commit(
                    ctx.root,
                    summary,
                    prefix=auto_commit_prefix(ctx.config),
                )
                if git_msg:
                    formatters.print_info(git_msg)

        formatters.print_success(
            "Session ended. Run `cognition-engine chat` or `cognition-engine start` for next session."
        )
    except Exception as e:
        _handle_error(e)


@app.command("upgrade")
def cmd_upgrade(
    refresh: bool = typer.Option(
        False,
        "--refresh",
        help="Force full re-download (same as CE_REFRESH=1)",
    ),
) -> None:
    """Pull latest Cognition Engine from GitHub and reinstall in the CE venv."""
    from src.core.env_guard import cognition_engine_home, cognition_venv_python, is_venv_active

    home = cognition_engine_home()
    pkg = home / "packages" / "cognition-engine"
    venv_py = cognition_venv_python()

    formatters.print_rule("Upgrade Cognition Engine")
    formatters.print_info(f"Install root: {home}")

    if refresh or not (home / ".git").is_dir():
        formatters.print_warning(
            "Run the installer to fetch latest source:\n"
            "  curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/install-ce.sh | bash\n"
            "Or force refresh:\n"
            "  CE_REFRESH=1 curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/install-ce.sh | bash"
        )
        raise typer.Exit(1)

    try:
        subprocess.run(["git", "-C", str(home), "fetch", "origin", "master"], check=True)
        subprocess.run(["git", "-C", str(home), "reset", "--hard", "origin/master"], check=True)
        formatters.print_success("Git source updated.")
    except subprocess.CalledProcessError as exc:
        formatters.print_error(f"git update failed: {exc}")
        raise typer.Exit(1) from exc

    pip_py = str(venv_py) if venv_py else sys.executable
    if not is_venv_active():
        formatters.print_info(f"Using CE venv: {pip_py}")
    subprocess.run([pip_py, "-m", "pip", "install", "-e", str(pkg), "--upgrade"], check=True)
    ce_bin = venv_py.parent / "cognition-engine" if venv_py else Path("cognition-engine")
    ver = subprocess.run([str(ce_bin), "--version"], capture_output=True, text=True, check=False)
    out = (ver.stdout or ver.stderr or "").strip() or "unknown"
    formatters.print_success(f"Upgraded: cognition-engine {out}")


@app.command("doctor")
def cmd_doctor() -> None:
    """Verify the installed package includes critical fixes."""
    import src
    from src.memory.session_tokens import session_tokens_consumed

    pkg_root = Path(src.__file__).resolve().parent
    checks: list[tuple[str, bool]] = [
        ("Package version >= 0.3.30", __version__ >= "0.3.30"),
        ("session_tokens.py present", (pkg_root / "memory" / "session_tokens.py").is_file()),
        (
            "Token dict normalization works",
            session_tokens_consumed({"tokens": {"total": 7}}) == 7,
        ),
    ]
    ks_path = pkg_root / "synthesizer" / "knowledge_synthesizer.py"
    if ks_path.is_file():
        ks_text = ks_path.read_text(encoding="utf-8")
        checks.append(
            (
                "Knowledge synthesizer uses session_tokens_consumed",
                "session_tokens_consumed" in ks_text,
            )
        )
        checks.append(
            (
                "Legacy int(tokens dict) pattern removed",
                'int(s.get("tokens_consumed", s.get("tokens"' not in ks_text,
            ),
        )

    from src.core.env_guard import env_warning_message, runtime_env_status

    formatters.print_rule("Install diagnostics")
    formatters.print_info(f"Version: {__version__}")
    formatters.print_info(f"Package path: {pkg_root}")
    env = runtime_env_status()
    if env.get("ce_venv_active"):
        formatters.print_success(
            f"CE runtime OK (venv: {env.get('ce_venv_dir') or env.get('ce_venv_python')})"
        )
    elif env.get("ce_venv_found"):
        formatters.print_info(
            f"CE venv: {env.get('ce_venv_dir')} — auto-used when you run cognition-engine"
        )
    elif env["venv_active"]:
        formatters.print_warning("Another venv is active; CE will switch to its own venv automatically")
    else:
        formatters.print_warning("CE venv not found — run install-ce.sh")
    warn = env_warning_message()
    if warn:
        formatters.print_warning(warn)
    try:
        import chromadb  # noqa: F401

        formatters.print_info("Install type: full/semantic (chromadb present)")
    except ImportError:
        formatters.print_info("Install type: slim (no chromadb — good for bandwidth)")
    failed = 0
    for label, ok in checks:
        if ok:
            formatters.print_success(label)
        else:
            formatters.print_error(label)
            failed += 1

    if failed:
        formatters.print_warning(
            "Reinstall (slim, uses venv — not system pip):\n"
            "  curl -fsSL https://raw.githubusercontent.com/Apar-Baral/CognitionEngine/master/scripts/install-ce.sh | bash"
        )
        raise typer.Exit(1)
    formatters.print_success("All checks passed.")


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
            parsed = _parse_value(value)
            ctx.config.update(key, parsed, persist=True)
            if key == "default_model":
                _print_model_updated(ctx, str(parsed))
            else:
                formatters.print_success(f"Set {key} = {value} (saved to .cognition/config.yaml)")
            raise typer.Exit(0)
        if key:
            val = ctx.config.get(key)
            formatters.print_info(f"{key} = {_mask(key, val)}")
    except Exception as e:
        _handle_error(e)


@app.command("chat")
def cmd_chat(
    project_path: Optional[Path] = typer.Option(None, "--project", "-p", help="Project root"),
    simple: bool = typer.Option(False, "--simple", help="Use stdin REPL instead of Textual"),
) -> None:
    """Launch interactive chat REPL."""
    try:
        from src.repl.repl_app import run_repl, run_repl_textual

        root = project_path or _state.get("project") or find_project_root()
        if simple:
            run_repl(Path(str(root)))
        else:
            run_repl_textual(Path(str(root)))
    except Exception as e:
        _handle_error(e)


@app.command("index")
def cmd_index(
    memory: bool = typer.Option(True, "--memory/--no-memory", help="Index vector memory from DNA"),
    graph: bool = typer.Option(True, "--graph/--no-graph", help="Rebuild architecture graph"),
) -> None:
    """Rebuild truth index, architecture graph, and vector memory."""
    try:
        ctx = _ctx()
        ctx.require_initialized()
        if graph:
            from src.memory.graph_indexer import index_architecture_graph

            index_architecture_graph(ctx.mutator, ctx.root)
            formatters.print_success("Architecture graph updated.")
        if memory:
            from src.memory.vector_store import VectorMemoryStore

            dna = ctx.query.refresh()
            store = VectorMemoryStore(ctx.root, ctx.project_name())
            store.index_tasks_from_dna(dna)
            formatters.print_success("Vector memory indexed (tasks).")
        from src.shield.truth_database import TruthDatabase

        db = TruthDatabase(ctx.root)
        db.index_codebase(progress_callback=lambda c, t, m: None)
        formatters.print_success("Truth index rebuilt.")
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
        pipeline = ctx.validation_pipeline(index_codebase=True)
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


def _llm_enrich_plan(
    ctx: ProjectContext, phase_list: list[dict[str, Any]], goal: str
) -> list[dict[str, Any]]:
    from src.planner.llm_planner import enrich_phases_with_llm

    formatters.print_info("Enriching plan with LLM…")
    return enrich_phases_with_llm(ctx, phase_list, goal)


def _apply_session_model(ctx: ProjectContext, model: Optional[str]) -> str:
    """Resolve model for session; persist and confirm when --model is passed."""
    if model:
        reg = ctx.model_registry()
        known = reg.list_models()
        if model not in known:
            formatters.print_warning(
                f"Model '{model}' is not in the registry. Known: {', '.join(known[:8])}"
                + ("..." if len(known) > 8 else "")
            )
        ctx.config.update("default_model", model, persist=True)
        _print_model_updated(ctx, model)
        return model
    active = str(ctx.config.get("default_model", "claude-sonnet"))
    formatters.print_info(f"Using model: {active} (set with --model ID to change)")
    return active


def _print_model_updated(ctx: ProjectContext, model_id: str) -> None:
    reg = ctx.model_registry()
    meta = reg.get_model(model_id) or {}
    label = meta.get("display_name") or model_id
    tier = meta.get("tier", "")
    tier_note = f" [{tier}]" if tier else ""
    formatters.print_success(f"Model updated to {model_id} ({label}){tier_note}")
    formatters.print_info("Saved in .cognition/config.yaml")


def _write_goal_file(ctx: ProjectContext, goal: str) -> None:
    if not goal.strip():
        return
    path = ctx.root / "GOAL.md"
    body = (
        "# Project goal\n\n"
        f"{goal.strip()}\n\n"
        "---\n\n"
        "_Managed by Cognition Engine (`cognition-engine goal --set`)._\n"
    )
    path.write_text(body, encoding="utf-8")
    formatters.print_info(f"Goal file: {path}")


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
