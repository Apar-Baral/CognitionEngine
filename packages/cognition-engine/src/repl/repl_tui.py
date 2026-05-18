"""Advanced Textual TUI — persistent commands, dropdown model select, searchable picker."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
    Select,
    Static,
)

from src.cli.context import resolve_project_root
from src.cli.model_picker import (
    apply_model_choice,
    format_models_table,
    models_grouped_by_tier,
    select_options_for_widget,
)
from src.cli.setup_summary import (
    format_setup_summary_rich,
    load_last_setup,
    load_project_setup_summary,
)
from src.repl.repl_theme import CE_APP_CSS
from src.repl.session_bridge import SessionBridge

COMMAND_BUTTONS: list[tuple[str, str, str]] = [
    ("btn-model", "Change model", "primary"),
    ("btn-start", "Start session", "primary"),
    ("btn-status", "Status", ""),
    ("btn-plan", "Generate plan", ""),
    ("btn-end", "End session", ""),
    ("btn-commit", "Git commit", ""),
    ("btn-setup", "Setup project", ""),
]

COMMAND_HINTS = """[dim]Chat:[/] type message + Enter
[dim]Keys:[/] Ctrl+M search models · PgUp/Dn scroll
[dim]End session:[/] use button — prompts in chat"""


class ModelPickerScreen(ModalScreen[str | None]):
    """Searchable model list — type to filter, Enter to pick, 1-9 quick pick."""

    CSS = """
    ModelPickerScreen { align: center middle; }
    #picker-frame {
        width: 92; max-width: 110; height: 88%;
        background: #111820; border: solid #6cb6ff; padding: 1 2;
    }
    #picker-search { margin-bottom: 1; border: solid #3d5a80; background: #0a0e14; }
    #picker-list { height: 1fr; border: solid #2d3a4f; background: #070b10; }
    #picker-footer { color: #768390; margin-top: 1; }
    """

    def __init__(self, bridge: SessionBridge) -> None:
        super().__init__()
        self.bridge = bridge
        self._entries: list[tuple[str, str]] = []  # (id, label)

    def compose(self) -> ComposeResult:
        current = str(self.bridge.ctx.config.get("default_model", ""))
        with Vertical(id="picker-frame"):
            yield Static(
                f"[bold #6cb6ff]Choose model[/]  [dim]active: {current}[/]",
                id="picker-title",
            )
            yield Input(placeholder="Search by name, id, or provider…", id="picker-search")
            yield ListView(id="picker-list")
            yield Static(
                "[dim]↑↓ move · Enter select · 1-9 quick pick · Esc close[/dim]",
                id="picker-footer",
            )

    def on_mount(self) -> None:
        self._rebuild_list("")
        self.query_one("#picker-search", Input).focus()

    def _rebuild_list(self, query: str) -> None:
        lv = self.query_one("#picker-list", ListView)
        lv.clear()
        current = str(self.bridge.ctx.config.get("default_model", ""))
        self._entries = []
        idx = 0
        for tier_name, items in models_grouped_by_tier(self.bridge.ctx.model_registry(), query=query):
            lv.mount(ListItem(Label(f"[bold #6cb6ff]— {tier_name} —"), id=f"hdr-{tier_name}"))
            for opt in items:
                idx += 1
                mid = opt["value"]
                mark = "[green]● [/green]" if mid == current else ""
                quick = f"[dim]{min(idx, 9)}[/dim] " if idx <= 9 else "   "
                label = f"{quick}{mark}{opt['select_label']}  [dim]{opt['provider']}[/dim]"
                lv.mount(ListItem(Label(label), id=f"m-{mid}"))
                self._entries.append((mid, opt["select_label"]))

    @on(Input.Changed, "#picker-search")
    def _on_search(self, event: Input.Changed) -> None:
        self._rebuild_list(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        if item_id.startswith("m-"):
            self.dismiss(item_id[2:])

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
            return
        if event.key in "123456789":
            n = int(event.key) - 1
            if n < len(self._entries):
                self.dismiss(self._entries[n][0])


class CognitionReplApp(App):
    """Professional agent console — no /help required."""

    TITLE = "Cognition Engine"
    SUB_TITLE = "Agent console"
    CSS = CE_APP_CSS
    BINDINGS = [
        Binding("ctrl+c", "request_quit", "Quit", show=True),
        Binding("ctrl+m", "pick_model", "Models", show=True),
        Binding("ctrl+s", "action_start", "Start", show=True),
        Binding("ctrl+e", "prompt_end", "End", show=True),
        Binding("ctrl+l", "clear_log", "Clear", show=False),
        Binding("pageup", "scroll_up", "▲", show=False),
        Binding("pagedown", "scroll_down", "▼", show=False),
    ]

    def __init__(self, project_root: Path | None = None) -> None:
        super().__init__()
        root = project_root or resolve_project_root()
        self.bridge = SessionBridge(root)
        self._agent = self._build_agent()

    def _build_agent(self):
        try:
            from src.agent.orchestrator import AgentOrchestrator

            return AgentOrchestrator(self.bridge.ctx)
        except Exception:
            return None

    def _try_bind_last_project(self) -> None:
        if self.bridge.ctx.is_initialized():
            return
        last = load_last_setup().get("project_path")
        if not last:
            return
        target = Path(str(last)).expanduser().resolve()
        if (target / ".cognition" / "dna.json").is_file():
            self.bridge.use_project(target)
            self._agent = self._build_agent()

    def _require_project(self, action: str = "This action") -> bool:
        if self.bridge.ctx.is_initialized():
            return True
        last = load_last_setup().get("project_path")
        self._log(
            f"[yellow]{action} needs a CE project.[/]\n"
            f"[dim]You are in[/] {self.bridge.root} [dim](not initialized).[/]"
        )
        if last:
            self._log(
                f"[dim]Fix:[/] cd {last}\n"
                f"      or type: [bold]/project {last}[/]"
            )
        else:
            self._log("[dim]Fix:[/] cognition-engine setup --project ~/projects/your-app")
        return False

    def _model_select_options(self) -> list[tuple[str, str]]:
        current = str(self.bridge.ctx.config.get("default_model", ""))
        opts = select_options_for_widget(
            self.bridge.ctx.model_registry(),
            current_id=current,
        )
        if opts:
            return opts
        return [("Default model", "claude-sonnet-4-20250514")]

    def _model_select_value(self, options: list[tuple[str, str]]) -> str:
        current = str(self.bridge.ctx.config.get("default_model", ""))
        if any(mid == current for _, mid in options):
            return current
        return options[0][1]

    def compose(self) -> ComposeResult:
        model_options = self._model_select_options()
        model_value = self._model_select_value(model_options)
        yield Header(show_clock=True)
        with Horizontal(id="workspace"):
            with Vertical(id="left-rail"):
                yield Static("MODEL", classes="rail-section-title")
                yield Select(
                    model_options,
                    id="model-select",
                    prompt="Select model…",
                    value=model_value,
                )
                yield Static(self._setup_panel_text(), id="setup-panel", markup=True)
                yield Static("ACTIONS", classes="rail-section-title")
                with Vertical(id="command-buttons"):
                    for bid, label, variant in COMMAND_BUTTONS:
                        yield Button(label, id=bid, classes="-primary" if variant == "primary" else "")
                yield Static(COMMAND_HINTS, id="command-hints", markup=True)
            with Vertical(id="main-column"):
                yield Static(self._top_bar_text(), id="top-bar", markup=True)
                with VerticalScroll(id="chat-scroll"):
                    yield RichLog(id="log", highlight=True, markup=True, wrap=True)
                with Horizontal(id="composer"):
                    yield Static("❯", id="prompt-glyph")
                    yield Input(
                        placeholder="Ask anything — slash commands optional",
                        id="input",
                    )
        yield Footer()

    def _setup_panel_text(self) -> str:
        return format_setup_summary_rich(
            load_last_setup(),
            load_project_setup_summary(self.bridge.root),
        )

    def _top_bar_text(self) -> str:
        reg = self.bridge.ctx.model_registry()
        mid = str(self.bridge.ctx.config.get("default_model", "—"))
        meta = reg.get_model(mid) or {}
        name = meta.get("display_name") or mid
        st = self.bridge.status_line()
        return (
            f"[bold #6cb6ff]{name}[/] [dim]({mid})[/]  "
            f"[dim]│[/]  {st}"
        )

    def _sync_model_select(self) -> None:
        sel = self.query_one("#model-select", Select)
        current = str(self.bridge.ctx.config.get("default_model", ""))
        options = select_options_for_widget(self.bridge.ctx.model_registry(), current_id=current)
        if not options:
            return
        sel.set_options(options)
        try:
            sel.value = current
        except Exception:
            if options:
                sel.value = options[0][1]

    def _refresh_chrome(self) -> None:
        self.query_one("#top-bar", Static).update(self._top_bar_text())
        self.query_one("#setup-panel", Static).update(self._setup_panel_text())
        self._sync_model_select()

    def _log(self, text: str) -> None:
        self.query_one(RichLog).write(text)
        self.query_one(VerticalScroll).scroll_end(animate=False)

    def on_mount(self) -> None:
        self._try_bind_last_project()
        self._sync_model_select()
        log = self.query_one(RichLog)
        log.write("[bold #6cb6ff]Cognition Engine[/] ready")
        log.write(
            "[dim]Use the left panel — pick a model from the dropdown or press[/] "
            "[bold]Change model[/][dim] to search. Buttons run actions; no /help needed.[/]"
        )
        if self.bridge.ctx.is_initialized():
            log.write(f"[dim]Project:[/] {self.bridge.root}")
            boot = self.bridge.get_bootstrap_text()
            if boot and not boot.startswith("Project not"):
                snippet = boot[:900] + "\n[dim]…[/]" if len(boot) > 900 else boot
                log.write(snippet)
        else:
            last = load_last_setup().get("project_path")
            if last:
                log.write(
                    f"[yellow]No project here.[/] [dim]Use[/] /project {last} "
                    f"[dim]or[/] cd {last}"
                )
            else:
                log.write("[yellow]Tip:[/] click [bold]Setup project[/] or: cognition-engine setup")

    @on(Select.Changed, "#model-select")
    def _on_model_dropdown(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK or event.value is None:
            return
        model_id = str(event.value)
        msg = apply_model_choice(self.bridge.ctx, model_id)
        self._log(f"[green]✓[/] {msg}")
        self._refresh_chrome()

    @on(Button.Pressed)
    def _on_command_button(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "btn-model":
            self.action_pick_model()
        elif bid == "btn-start":
            if self._require_project("Start session"):
                self.action_start()
        elif bid == "btn-status":
            if self._require_project("Status"):
                self._run_bridge(lambda: self.bridge.cmd_status())
        elif bid == "btn-plan":
            self._prompt_plan()
        elif bid == "btn-end":
            if self._require_project("End session"):
                self.action_prompt_end()
        elif bid == "btn-commit":
            if self._require_project("Git commit"):
                self._prompt_commit()
        elif bid == "btn-setup":
            self._run_bridge(lambda: self.bridge.cmd_setup())
            self._agent = self._build_agent()

    def _run_bridge(self, fn) -> None:
        try:
            result = fn()
            if result:
                self._log(result)
            self._refresh_chrome()
        except Exception as exc:
            from src.core.exceptions import DNALoadError

            if isinstance(exc, DNALoadError):
                self._require_project("This command")
            else:
                self._log(f"[red]{exc}[/]")

    def _prompt_plan(self) -> None:
        if not self._require_project("Generate plan"):
            return
        goal = self.bridge.ctx.get_project_goal()
        if goal:
            self._run_bridge(lambda: self.bridge.cmd_plan(""))
        else:
            self._log("[yellow]Set a goal first[/] — type: /goal Your project objective")
            self.query_one("#input", Input).value = "/goal "
            self.query_one("#input", Input).focus()

    def action_prompt_end(self) -> None:
        self._log("[dim]Type your session summary after /end — e.g.[/] /end Finished auth module")
        self.query_one("#input", Input).value = "/end "
        self.query_one("#input", Input).focus()

    def _prompt_commit(self) -> None:
        self.query_one("#input", Input).value = "/commit "
        self.query_one("#input", Input).focus()
        self._log("[dim]Describe the commit:[/] /commit your message")

    def action_start(self) -> None:
        self._run_bridge(lambda: self.bridge.cmd_start())

    def action_pick_model(self) -> None:
        self.push_screen(ModelPickerScreen(self.bridge), self._on_model_picked)

    def _on_model_picked(self, model_id: str | None) -> None:
        if not model_id:
            return
        msg = apply_model_choice(self.bridge.ctx, model_id)
        self._log(f"[green]✓[/] {msg}")
        self._refresh_chrome()

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

        self._log(f"[bold #6cb6ff]you[/]  {line}")

        if line.startswith("/"):
            cmd = line.split(maxsplit=1)[0].lower()
            if cmd in ("/model", "/models") and cmd == "/model" and line.strip().lower() == "/model":
                self.action_pick_model()
                return
            result = self.bridge.dispatch(line)
            if result == "__EXIT__":
                self.exit()
                return
            if line.split(maxsplit=1)[0].lower() in ("/project", "/cd", "/setup"):
                self._agent = self._build_agent()
            if result:
                if cmd == "/models":
                    self._log(format_models_table(self.bridge.ctx.model_registry()))
                else:
                    self._log(result)
            self._refresh_chrome()
            return

        if self._agent:
            self._log("[dim italic]Thinking…[/]")
            try:
                reply = self._agent.chat(line)
                self._log(f"[bold #79c0ff]assistant[/]\n{reply}")
            except Exception as exc:
                self._log(f"[red]Error: {exc}[/]")
        else:
            self._log("[yellow]Add API keys in ~/.cognition/config.yaml[/] — buttons still work for planning/git")
        self._refresh_chrome()
