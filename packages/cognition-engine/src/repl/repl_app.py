"""Simple interactive REPL (stdin/stdout) — works without full TUI."""

from __future__ import annotations

import sys
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from src.cli.context import find_project_root
from src.repl.repl_commands import is_chat_message, is_slash_command
from src.repl.session_bridge import SessionBridge


def run_repl(project_root: Path | None = None) -> None:
    """Run interactive Cognition Engine REPL."""
    root = project_root or find_project_root()
    bridge = SessionBridge(root)
    console = Console()

    console.print(
        Panel(
            "[bold]Cognition Engine[/bold] — interactive mode\n"
            "Type /help for commands, or chat after /start.\n"
            "Tip: cognition-engine setup --project .  for first-time init",
            title="CE Chat",
        )
    )

    if not bridge.ctx.is_initialized():
        console.print("[yellow]No .cognition/ found. Run /setup or: cognition-engine setup --project .[/]")

    agent = None
    try:
        from src.agent.orchestrator import AgentOrchestrator

        agent = AgentOrchestrator(bridge.ctx)
    except Exception:
        pass

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
                if line in ("/bootstrap",) or result.startswith("╔"):
                    console.print(result)
                else:
                    console.print(Panel(result, border_style="green"))
            continue

        if is_chat_message(line):
            if agent is None:
                console.print(
                    "[yellow]Agent unavailable (API keys?). Use slash commands or configure ~/.cognition/config.yaml[/]"
                )
                continue
            console.print("[dim]Thinking…[/]")
            try:
                reply = agent.chat(line)
                console.print(Panel(Markdown(reply), title="Assistant", border_style="blue"))
            except Exception as exc:
                console.print(f"[red]Error: {exc}[/]")
            continue

        console.print("[dim]Unknown input. Try /help[/]")


def run_repl_textual(project_root: Path | None = None) -> None:
    """Try Textual TUI; fall back to simple REPL."""
    try:
        from src.repl.repl_tui import CognitionReplApp

        app = CognitionReplApp(project_root)
        app.run()
    except Exception:
        run_repl(project_root)


if __name__ == "__main__":
    run_repl_textual()
