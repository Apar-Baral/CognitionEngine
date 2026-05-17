from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from cognition_engine.cli import formatters
from cognition_engine.core.exceptions import (
    CognitionEngineError,
    DnaNotFoundError,
    NoActiveSessionError,
)
from cognition_engine.core.paths import cognition_dir, find_project_root
from cognition_engine.service import CognitionService

app = typer.Typer(
    name="ce",
    help="Cognition Engine — persistent memory for AI-assisted development",
    no_args_is_help=True,
)
adapter_app = typer.Typer(help="Host adapters (Cursor, Claude Code)")
app.add_typer(adapter_app, name="adapter")


def _service() -> CognitionService:
    return CognitionService()


@app.command("init")
def cmd_init(
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Project name"),
    meta_tool: bool = typer.Option(
        False,
        "--meta-tool",
        help="Use Cognition Engine self-build phase plan",
    ),
) -> None:
    """Initialize Cognition Engine for the current project."""
    try:
        svc = _service()
        dna = svc.init_project(name=name, meta_tool=meta_tool)
        formatters.print_success(f"Initialized {dna['project']['name']}")
        formatters.print_info(f"DNA: {cognition_dir(svc.root) / 'dna.json'}")
        phases = len(dna["master_plan"]["phases"])
        formatters.print_info(f"Plan: {phases} phases")
        typer.echo(svc.status())
    except CognitionEngineError as e:
        formatters.print_error(str(e))
        raise typer.Exit(1) from e


@app.command("start")
def cmd_start(
    session_type: str = typer.Option("BUILD", "--type", "-t", help="Session type"),
    budget: Optional[int] = typer.Option(None, "--budget", "-b", help="Token budget"),
    print_only: bool = typer.Option(False, "--print", help="Print bootstrap only"),
    adapter: Optional[str] = typer.Option(
        None, "--adapter", "-a", help="Also install to adapter: cursor|claude_code"
    ),
) -> None:
    """Start a session and generate bootstrap context."""
    try:
        svc = _service()
        dna, packet = svc.start_session(session_type=session_type, budget=budget)
        bootstrap_path = cognition_dir(svc.root) / "bootstrap.md"
        formatters.print_success(f"Session started — {dna.get('current_phase_id')}")
        formatters.print_info(f"Bootstrap: {bootstrap_path} (~{packet.estimated_tokens} tokens)")

        if adapter:
            _run_adapter_install(adapter, svc.root, packet.markdown)

        if print_only:
            typer.echo(packet.markdown)
        else:
            formatters.print_panel("Bootstrap preview", packet.markdown[:2000])
    except CognitionEngineError as e:
        formatters.print_error(str(e))
        raise typer.Exit(1) from e


@app.command("end")
def cmd_end(
    summary: str = typer.Option(..., "--summary", "-s", help="Session summary"),
    tokens: int = typer.Option(0, "--tokens", help="Tokens used this session"),
    files: Optional[str] = typer.Option(
        None, "--files", help="Comma-separated modified files"
    ),
    complete: bool = typer.Option(
        False, "--complete", help="Mark current sub-task completed"
    ),
) -> None:
    """End the active session and persist progress."""
    try:
        file_list = [f.strip() for f in files.split(",")] if files else []
        svc = _service()
        svc.end_session(
            summary=summary,
            tokens=tokens,
            files=file_list,
            complete_sub_task=complete,
        )
        formatters.print_success("Session ended and DNA updated")
        typer.echo(svc.status())
    except CognitionEngineError as e:
        formatters.print_error(str(e))
        raise typer.Exit(1) from e


@app.command("status")
def cmd_status() -> None:
    """Show progress map and session state."""
    try:
        typer.echo(_service().status())
    except DnaNotFoundError as e:
        formatters.print_error(str(e))
        raise typer.Exit(1) from e


@app.command("budget")
def cmd_budget(
    set_budget: Optional[int] = typer.Option(None, "--set", help="Set session budget"),
) -> None:
    """Show or set session token budget."""
    try:
        svc = _service()
        if set_budget is not None:
            dna = svc.store.load()
            from cognition_engine.dna.mutator import DnaMutator

            DnaMutator(dna).set_session_budget(set_budget)
            svc.store.save(dna)
            formatters.print_success(f"Budget set to {set_budget:,} tokens")
        for line in svc.budget_status():
            typer.echo(line)
    except DnaNotFoundError as e:
        formatters.print_error(str(e))
        raise typer.Exit(1) from e


@app.command("index")
def cmd_index() -> None:
    """Rebuild truth index from codebase (Python)."""
    try:
        idx = _service().refresh_truth_index()
        formatters.print_success(f"Indexed {len(idx.modules)} modules")
    except CognitionEngineError as e:
        formatters.print_error(str(e))
        raise typer.Exit(1) from e


@app.command("validate")
def cmd_validate(
    module: Optional[str] = typer.Option(None, "--import", help="Import module name"),
    file: Optional[Path] = typer.Option(None, "--file", help="Python file to validate"),
) -> None:
    """Validate imports against truth index (Stage-1 shield)."""
    try:
        svc = _service()
        if module:
            r = svc.validate_import(module)
            if r.valid:
                formatters.print_success(f"OK: {module}")
            else:
                formatters.print_error(r.message)
                if r.suggestion:
                    formatters.print_info(f"Did you mean: {r.suggestion}?")
                raise typer.Exit(1)
        elif file:
            results = svc.validate_file(file)
            if not results:
                formatters.print_success("No import issues found")
            else:
                for r in results:
                    formatters.print_error(f"{r.proposed}: {r.message}")
                raise typer.Exit(1)
        else:
            formatters.print_error("Provide --import or --file")
            raise typer.Exit(1)
    except DnaNotFoundError as e:
        formatters.print_error(str(e))
        raise typer.Exit(1) from e


@app.command("shield-record")
def cmd_shield_record(
    proposed: str = typer.Option(..., "--proposed"),
    correct: str = typer.Option(..., "--correct"),
    category: str = typer.Option("import_invention", "--category"),
) -> None:
    """Record a hallucination in the avoid register."""
    svc = _service()
    svc.record_hallucination(proposed, correct, category)
    formatters.print_success("Recorded in avoid_registry")


@adapter_app.command("install")
def cmd_adapter_install(
    name: str = typer.Argument(..., help="cursor or claude_code"),
) -> None:
    """Install host adapter to sync bootstrap to Cursor or Claude Code."""
    root = find_project_root()
    bootstrap = cognition_dir(root) / "bootstrap.md"
    if not bootstrap.is_file():
        formatters.print_error("No bootstrap.md — run `ce start` first")
        raise typer.Exit(1)
    md = bootstrap.read_text(encoding="utf-8")
    _run_adapter_install(name, root, md)
    formatters.print_success(f"Adapter '{name}' installed")


def _run_adapter_install(name: str, root: Path, markdown: str) -> None:
    if name == "cursor":
        from cognition_engine.adapters.cursor import install_cursor

        install_cursor(root, markdown)
    elif name in ("claude_code", "claude"):
        from cognition_engine.adapters.claude_code import install_claude_code

        install_claude_code(root, markdown)
    else:
        raise typer.BadParameter(f"Unknown adapter: {name}")


if __name__ == "__main__":
    app()
