"""Interactive REPL — Textual TUI with rich fallback."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from src.cli.context import resolve_project_root
from src.repl.repl_commands import is_chat_message, is_slash_command
from src.repl.session_bridge import SessionBridge


def run_repl(project_root: Path | None = None) -> None:
    """Rich stdin REPL — full commands, memory/RL."""
    root = resolve_project_root(project_root)
    bridge = SessionBridge(root)
    console = Console()

    model = bridge.ctx.config.get("default_model", "?")
    console.print(
        Panel(
            "[bold]Cognition Engine[/bold] — line mode (agent console UI failed or CE_SIMPLE_REPL=1)\n"
            f"Project: {bridge.root} | Model: {model}\n"
            "[dim]Memory + RL on /end · /model or Ctrl+M in full UI[/]\n"
            "Commands: /help /start /end /memory /rl /keys /model /plan /status /setup",
            title="CE line mode",
            border_style="blue",
        )
    )

    if not bridge.ctx.is_initialized():
        console.print("[yellow]Project not initialized.[/] Run: /setup")

    def _live(msg: str) -> None:
        console.print(f"[dim]⚙ {msg}[/]")

    def _perm(category: str, detail: str):
        from src.repl.permission_prompt import ask_permission

        return ask_permission(console, category, detail)

    agent = None
    try:
        from src.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator(
            bridge.ctx, on_activity=_live, on_permission=_perm
        )
    except Exception as exc:
        console.print(f"[dim]Chat disabled until API keys configured:[/] {exc}")

    while True:
        try:
            status = bridge.status_line()
            line = console.input(f"[cyan]ce[/cyan] ({status})> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/]")
            break

        if not line:
            continue

        if is_slash_command(line):
            result = bridge.dispatch(line)
            if result == "__EXIT__":
                break
            if result:
                if line.split()[0].lower() in ("/bootstrap",):
                    console.print(result)
                else:
                    console.print(Panel(result, border_style="green"))
            if line.split()[0].lower() in ("/setup", "/project", "/cd"):
                try:
                    from src.agent.orchestrator import AgentOrchestrator

                    agent = AgentOrchestrator(
                        bridge.ctx, on_activity=_live, on_permission=_perm
                    )
                except Exception as exc:
                    console.print(f"[yellow]{exc}[/]")
            continue

        if is_chat_message(line):
            if agent is None:
                try:
                    from src.agent.orchestrator import AgentOrchestrator

                    agent = AgentOrchestrator(
                        bridge.ctx, on_activity=_live, on_permission=_perm
                    )
                except Exception as exc:
                    console.print(f"[red]{exc}[/]")
                    console.print("[dim]Fix:[/] /keys  or  /setup")
                    continue
            console.print("[dim]Agentic mode — watch ⚙ lines for each file/command…[/]")
            try:
                reply = agent.chat(line)
                console.print(Panel(Markdown(reply), title="Assistant", border_style="blue"))
            except Exception as exc:
                console.print(f"[red]Error: {exc}[/]")
                console.print("[dim]Check:[/] /keys — model provider must match your API key")
            continue

        console.print("[dim]Unknown input. Try /help[/]")


def run_repl_textual(project_root: Path | None = None) -> None:
    """Textual TUI; falls back to rich REPL with error shown once."""
    # Default: full agent console (Textual). Fallback: rich line mode.
    if os.environ.get("CE_SIMPLE_REPL") == "1":
        run_repl(project_root)
        return
    try:
        from src.repl.repl_tui import CognitionReplApp

        app = CognitionReplApp(project_root)
        app.run_app()
    except Exception as exc:
        console = Console(stderr=True)
        console.print(f"[yellow]Agent console UI unavailable ({exc}).[/]")
        if os.environ.get("CE_REPL_DEBUG"):
            traceback.print_exc()
        console.print(
            "[dim]Using line mode (same commands). "
            "Force UI: unset CE_SIMPLE_REPL · Force line: CE_SIMPLE_REPL=1[/]\n"
        )
        run_repl(project_root)


if __name__ == "__main__":
    run_repl_textual()
