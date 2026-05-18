"""Professional Textual TUI for Cognition Engine REPL."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, RichLog, Static

from src.cli.context import find_project_root
from src.cli.model_picker import format_models_table
from src.cli.setup_summary import (
    format_setup_summary_rich,
    load_last_setup,
    load_project_setup_summary,
)
from src.repl.session_bridge import SessionBridge


CE_CSS = """
Screen {
    background: #0d1117;
}

#body {
    height: 1fr;
}

#sidebar {
    width: 36;
    min-width: 28;
    max-width: 42;
    background: #161b22;
    border-right: solid #30363d;
    padding: 1 1;
}

#sidebar-title {
    text-style: bold;
    color: #58a6ff;
    margin-bottom: 1;
}

#setup-panel {
    color: #c9d1d9;
}

#chat-column {
    width: 1fr;
}

#status-bar {
    height: 3;
    background: #21262d;
    border: solid #30363d;
    padding: 0 1;
    color: #8b949e;
}

#chat-scroll {
    height: 1fr;
    border: solid #30363d;
    background: #010409;
    scrollbar-gutter: stable;
}

#log {
    height: auto;
    min-height: 100%;
    padding: 0 1;
}

#input-row {
    height: auto;
    margin-top: 1;
    border-top: solid #30363d;
    padding-top: 1;
}

#input {
    border: tall #388bfd;
    background: #0d1117;
}

#input-label {
    width: 8;
    content-align: center middle;
    color: #58a6ff;
    text-style: bold;
}

ModelSelectScreen {
    align: center middle;
}

#model-dialog {
    width: 80%;
    max-width: 90;
    height: 70%;
    background: #161b22;
    border: solid #388bfd;
    padding: 1 2;
}

#model-hint {
    margin-bottom: 1;
    color: #8b949e;
}

#model-list {
    height: 1fr;
    border: solid #30363d;
    background: #0d1117;
}
"""


class ModelSelectScreen(ModalScreen[str | None]):
    """Hermes-style model list (keyboard navigable)."""

    CSS = """
    ModelSelectScreen {
        align: center middle;
    }
  #model-dialog {
        width: 85;
        max-width: 95;
        height: 75%;
        background: #161b22;
        border: solid #388bfd;
        padding: 1 2;
    }
    #model-list {
        height: 1fr;
        border: solid #30363d;
        background: #0d1117;
    }
    """

    def __init__(self, bridge: SessionBridge) -> None:
        super().__init__()
        self.bridge = bridge

    def compose(self) -> ComposeResult:
        reg = self.bridge.ctx.model_registry()
        current = str(self.bridge.ctx.config.get("default_model", ""))
        with Vertical(id="model-dialog"):
            yield Static(
                f"[bold]Select model[/]  [dim]current: {current}[/]\n"
                "[dim]↑↓ navigate · Enter select · Esc cancel[/]",
                id="model-hint",
            )
            items = []
            for mid in reg.list_models()[:40]:
                meta = reg.get_model(mid) or {}
                label = f"{mid}  —  {meta.get('display_name', mid)}  [{meta.get('tier', '?')}]"
                if mid == current:
                    label = f"● {label}"
                items.append(ListItem(Label(label), id=f"m-{mid}"))
            yield ListView(*items, id="model-list")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("m-"):
            self.dismiss(item_id[2:])
        else:
            self.dismiss(None)

    def key_escape(self) -> None:
        self.dismiss(None)


class CognitionReplApp(App):
    """Scrollable chat, setup summary sidebar, model picker."""

    TITLE = "Cognition Engine"
    SUB_TITLE = "Interactive agent"
    CSS = CE_CSS
    BINDINGS = [
        Binding("ctrl+c", "request_quit", "Quit", show=True),
        Binding("ctrl+d", "request_quit", "Quit", show=False),
        Binding("ctrl+m", "pick_model", "Model", show=True),
        Binding("ctrl+l", "clear_log", "Clear", show=True),
        Binding("pageup", "scroll_up", "Scroll up", show=False),
        Binding("pagedown", "scroll_down", "Scroll down", show=False),
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
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            yield Static(self._setup_panel_text(), id="setup-panel", markup=True)
            with Vertical(id="chat-column"):
                yield Static(self._status_text(), id="status-bar", markup=True)
                with VerticalScroll(id="chat-scroll"):
                    yield RichLog(id="log", highlight=True, markup=True, wrap=True)
                with Horizontal(id="input-row"):
                    yield Static("›", id="input-label")
                    yield Input(
                        placeholder="Message or /command  (/help · Ctrl+M model)",
                        id="input",
                    )
        yield Footer()

    def _setup_panel_text(self) -> str:
        return format_setup_summary_rich(
            load_last_setup(),
            load_project_setup_summary(self.bridge.root),
        )

    def _status_text(self) -> str:
        st = self.bridge.status_line()
        try:
            from src.core.env_guard import is_venv_active

            env = "[green]venv[/]" if is_venv_active() else "[yellow]system py[/]"
        except ImportError:
            env = ""
        return f"[bold #58a6ff]●[/] {st}  {env}"

    def _refresh_status(self) -> None:
        self.query_one("#status-bar", Static).update(self._status_text())

    def _refresh_setup_panel(self) -> None:
        self.query_one("#setup-panel", Static).update(self._setup_panel_text())

    def on_mount(self) -> None:
        self._refresh_setup_panel()
        log = self.query_one(RichLog)
        log.write("[bold #58a6ff]Cognition Engine[/] — professional mode")
        log.write("[dim]/help[/] commands · [dim]Ctrl+M[/] model picker · [dim]PgUp/PgDn[/] scroll chat")
        if not self.bridge.ctx.is_initialized():
            log.write("[yellow]Run[/] [bold]/setup[/] or: cognition-engine setup --project .")
        else:
            boot = self.bridge.get_bootstrap_text()
            if boot and not boot.startswith("Project not"):
                if len(boot) > 1200:
                    log.write(boot[:1200] + "\n[dim]… (scroll for more)[/]")
                else:
                    log.write(boot)

    def action_pick_model(self) -> None:
        self.push_screen(ModelSelectScreen(self.bridge), self._on_model_picked)

    def _on_model_picked(self, model_id: str | None) -> None:
        if not model_id:
            return
        result = self.bridge.cmd_model(model_id)
        log = self.query_one(RichLog)
        log.write(f"[green]{result}[/]")
        self._refresh_status()
        self._refresh_setup_panel()

    def action_clear_log(self) -> None:
        self.query_one(RichLog).clear()

    def action_scroll_up(self) -> None:
        self.query_one(VerticalScroll).scroll_up(animate=False)

    def action_scroll_down(self) -> None:
        self.query_one(VerticalScroll).scroll_down(animate=False)

    def action_request_quit(self) -> None:
        self.exit()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        line = event.value.strip()
        event.input.value = ""
        if not line:
            return
        log = self.query_one(RichLog)
        scroll = self.query_one(VerticalScroll)
        log.write(f"[bold cyan]you ›[/] {line}")

        if line.startswith("/"):
            cmd = line.split(maxsplit=1)[0].lower()
            if cmd == "/model" and line.strip().lower() == "/model":
                self.action_pick_model()
                return
            result = self.bridge.dispatch(line)
            if result == "__EXIT__":
                self.exit()
                return
            if result:
                if cmd == "/models":
                    log.write(format_models_table(self.bridge.ctx.model_registry()))
                else:
                    log.write(result)
            self._refresh_status()
            scroll.scroll_end(animate=False)
            return

        if self._agent:
            log.write("[dim italic]Thinking…[/]")
            scroll.scroll_end(animate=False)
            try:
                reply = self._agent.chat(line)
                log.write(f"[bold #79c0ff]assistant ›[/]\n{reply}")
            except Exception as exc:
                log.write(f"[red]Error: {exc}[/]")
        else:
            log.write("[yellow]Set API keys in ~/.cognition/config.yaml or use /commands[/]")
        self._refresh_status()
        scroll.scroll_end(animate=False)
