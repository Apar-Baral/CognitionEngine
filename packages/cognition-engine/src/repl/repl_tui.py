"""Textual TUI for Cognition Engine REPL."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Footer, Header, Input, RichLog

from src.cli.context import find_project_root
from src.repl.session_bridge import SessionBridge


class CognitionReplApp(App):
    """Chat log + command input."""

    TITLE = "Cognition Engine"
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+d", "quit", "Quit"),
    ]

    def __init__(self, project_root: Path | None = None) -> None:
        super().__init__()
        root = project_root or find_project_root()
        self.bridge = SessionBridge(root)
        self._agent = None
        try:
            from src.agent.orchestrator import AgentOrchestrator

            self._agent = AgentOrchestrator(self.bridge.ctx)
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        yield Header()
        yield Vertical(
            RichLog(id="log", highlight=True, markup=True),
            Input(placeholder="Message or /command …", id="input"),
            id="main",
        )
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one(RichLog)
        log.write("[bold]Cognition Engine[/] — /help for commands")
        if not self.bridge.ctx.is_initialized():
            log.write("[yellow]Run /setup to initialize project[/]")

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        line = event.value.strip()
        event.input.value = ""
        if not line:
            return
        log = self.query_one(RichLog)
        log.write(f"[cyan]you>[/] {line}")

        if line.startswith("/"):
            result = self.bridge.dispatch(line)
            if result == "__EXIT__":
                self.exit()
                return
            if result:
                log.write(result)
            return

        if self._agent:
            log.write("[dim]Thinking…[/]")
            try:
                reply = self._agent.chat(line)
                log.write(f"[bold blue]assistant>[/]\n{reply}")
            except Exception as exc:
                log.write(f"[red]Error: {exc}[/]")
        else:
            log.write("[yellow]Configure API keys for chat, or use /commands[/]")
