"""Advanced Textual TUI — persistent commands, dropdown model select, searchable picker."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.timer import Timer
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
from textual.worker import Worker, WorkerState

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
from src.repl.repl_theme import CE_APP_CSS, CE_BRAND_MARKUP
from src.repl.session_bridge import SessionBridge

COMMAND_BUTTONS: list[tuple[str, str, str]] = [
    ("btn-model", "Change model", "primary"),
    ("btn-start", "Start session", "primary"),
    ("btn-plan", "Generate plan", "primary"),
    ("btn-show-plan", "Show plan", ""),
    ("btn-status", "Track progress", ""),
    ("btn-end", "End session", ""),
    ("btn-commit", "Git hint", ""),
    ("btn-setup", "Setup keys", "primary"),
    ("btn-quit", "Exit CE", "danger"),
]

COMMAND_HINTS = """[dim]Chat:[/] center · trace panel right
[dim]Copy:[/] drag-select text in chat/trace
[dim]Git:[/] you commit in your shell — CE won't"""

_THINK_FRAMES = ("◐", "◓", "◑", "◒")


@dataclass(frozen=True)
class ChatJobResult:
    kind: str
    payload: str = ""


class ConfirmQuitScreen(ModalScreen[bool]):
    """Confirm before closing the agent console."""

    def compose(self) -> ComposeResult:
        with Vertical(id="quit-frame"):
            yield Static("[bold #f85149]Exit Cognition Engine?[/]", id="quit-title")
            yield Static("[dim]Unsaved chat is kept in this session only.[/dim]", markup=True)
            with Horizontal(id="quit-actions"):
                yield Button("Exit", id="quit-yes", variant="error")
                yield Button("Stay", id="quit-no")

    @on(Button.Pressed, "#quit-yes")
    def _yes(self, _event: Button.Pressed) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#quit-no")
    def _no(self, _event: Button.Pressed) -> None:
        self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
        elif event.key in ("enter", "y"):
            self.dismiss(True)


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
        self._entries: list[tuple[str, str]] = []  # (model_id, label)
        self._id_to_mid: dict[str, str] = {}

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
        self._id_to_mid = {}
        slot = 0
        pick_idx = 0
        for tier_name, items in models_grouped_by_tier(self.bridge.ctx.model_registry(), query=query):
            hdr_id = f"picker-hdr-{slot}"
            slot += 1
            lv.mount(ListItem(Label(f"[bold #6cb6ff]— {tier_name} —"), id=hdr_id))
            for opt in items:
                pick_idx += 1
                mid = opt["value"]
                item_id = f"picker-model-{slot}"
                slot += 1
                self._id_to_mid[item_id] = mid
                mark = "[green]● [/green]" if mid == current else ""
                quick = f"[dim]{min(pick_idx, 9)}[/dim] " if pick_idx <= 9 else "   "
                label = f"{quick}{mark}{opt['select_label']}  [dim]{opt['provider']}[/dim]"
                lv.mount(ListItem(Label(label), id=item_id))
                self._entries.append((mid, opt["select_label"]))

    @on(Input.Changed, "#picker-search")
    def _on_search(self, event: Input.Changed) -> None:
        self._rebuild_list(event.value)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        mid = self._id_to_mid.get(item_id)
        if mid:
            self.dismiss(mid)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)
            return
        if event.key in "123456789":
            n = int(event.key) - 1
            if n < len(self._entries):
                self.dismiss(self._entries[n][0])


class QuickSetupScreen(ModalScreen[bool]):
    """Model + API key setup inside Textual (no Rich terminal prompts)."""

    DEFAULT_CSS = """
    QuickSetupScreen { align: center middle; }
    #setup-frame {
        width: 88; max-width: 96; height: auto;
        background: #111820; border: solid #6cb6ff; padding: 1 2;
    }
    #setup-api-key { margin: 1 0; border: solid #3d5a80; background: #0a0e14; }
    #setup-actions { height: auto; margin-top: 1; }
    #setup-actions Button { margin-right: 1; }
    """

    def __init__(self, bridge: SessionBridge) -> None:
        super().__init__()
        self.bridge = bridge
        self._model_id = str(bridge.ctx.config.get("default_model", ""))

    def compose(self) -> ComposeResult:
        with Vertical(id="setup-frame"):
            yield Static("[bold #6cb6ff]Setup — model & API key[/]", id="setup-title")
            yield Static("", id="setup-model-line", markup=True)
            yield Button("Choose model…", id="setup-pick-model")
            yield Static("", id="setup-provider-hint", markup=True)
            yield Input(
                placeholder="Paste API key (blank if already in env)",
                id="setup-api-key",
                password=True,
            )
            with Horizontal(id="setup-actions"):
                yield Button("Save", id="setup-save", variant="primary")
                yield Button("Later", id="setup-skip")

    def on_mount(self) -> None:
        self._refresh_model_line()
        self.query_one("#setup-api-key", Input).focus()

    def _refresh_model_line(self) -> None:
        from src.cli.hermes_setup import _ENV_KEYS, _PROVIDER_LABELS
        from src.cli.model_picker import resolve_model_id

        reg = self.bridge.ctx.model_registry()
        mid = resolve_model_id(self._model_id, reg) or self._model_id or "claude-haiku-20240307"
        self._model_id = mid
        meta = reg.get_model(mid) or {}
        name = meta.get("display_name") or mid
        prov = str(meta.get("provider") or "openai")
        self.query_one("#setup-model-line", Static).update(
            f"Model: [cyan]{name}[/] [dim]({mid})[/]"
        )
        label = _PROVIDER_LABELS.get(prov, prov)
        env_var = _ENV_KEYS.get(prov, "OPENAI_API_KEY")
        self.query_one("#setup-provider-hint", Static).update(
            f"[dim]API key for {label} · or export {env_var}[/]"
        )

    @on(Button.Pressed, "#setup-pick-model")
    def _pick_model(self, _event: Button.Pressed) -> None:
        self.app.push_screen(ModelPickerScreen(self.bridge), self._on_model_picked)

    def _on_model_picked(self, model_id: str | None) -> None:
        if model_id:
            self._model_id = model_id
            self._refresh_model_line()

    @on(Button.Pressed, "#setup-save")
    def _save(self, _event: Button.Pressed) -> None:
        from src.cli.hermes_setup import persist_setup_choices

        key = self.query_one("#setup-api-key", Input).value.strip()
        persist_setup_choices(
            self._model_id,
            api_key=key or None,
            project_root=self.bridge.root,
            init_project=True,
        )
        self.dismiss(True)

    @on(Button.Pressed, "#setup-skip")
    def _skip(self, _event: Button.Pressed) -> None:
        self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)


class CognitionReplApp(App):
    """Professional agent console — no /help required."""

    ENABLE_TEXT_SELECTION = True

    TITLE = "Cognition Engine"
    SUB_TITLE = "Agent console"
    CSS = CE_APP_CSS
    BINDINGS = [
        Binding("ctrl+q", "confirm_quit", "Exit", show=True),
        Binding("ctrl+c", "confirm_quit", "Exit", show=False),
        Binding("escape", "handle_escape", "Cancel", show=True),
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
        self._select_syncing = False
        self._active_model_id = str(self.bridge.ctx.config.get("default_model", ""))
        self._thinking_timer: Timer | None = None
        self._thinking_tick = 0
        self._chat_busy = False
        self._last_user_prompt = ""

    def _build_agent(self):
        try:
            from src.agent.orchestrator import AgentOrchestrator

            return AgentOrchestrator(self.bridge.ctx, on_activity=self._on_agent_activity)
        except Exception:
            return None

    def _on_agent_activity(self, msg: str) -> None:
        try:
            self.call_from_thread(self._log_work, msg)
        except RuntimeError:
            self._log_work(msg)

    def _try_bind_last_project(self) -> None:
        """Do not auto-switch to a different directory than cwd (avoids surprise project context)."""
        return

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
            with VerticalScroll(id="left-rail", can_focus=True):
                with Vertical(id="left-rail-inner"):
                    yield Static(CE_BRAND_MARKUP, id="ce-brand", markup=True)
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
                            classes = ""
                            if variant == "primary":
                                classes = "-primary"
                            elif variant == "danger":
                                classes = "-danger"
                            yield Button(label, id=bid, classes=classes)
                    yield Static(COMMAND_HINTS, id="command-hints", markup=True)
            with Vertical(id="chat-column"):
                yield Static(self._top_bar_text(), id="top-bar", markup=True)
                yield Static(self._tracker_text(), id="tracker-panel", markup=True)
                yield Static(
                    "[dim]Your message appears below when you send[/]",
                    id="prompt-display",
                    markup=True,
                )
                with VerticalScroll(id="chat-scroll", can_focus=True):
                    yield RichLog(id="log", highlight=True, markup=True, wrap=True)
                with Horizontal(id="composer"):
                    yield Static("❯", id="prompt-glyph")
                    yield Input(
                        placeholder="Ask anything — slash commands optional",
                        id="input",
                    )
            with Vertical(id="trace-rail"):
                yield Static("AGENT TRACE", classes="rail-section-title")
                yield Static("", id="thinking-bar", markup=True)
                with VerticalScroll(id="activity-scroll", can_focus=True):
                    yield RichLog(id="activity-log", highlight=False, markup=True, wrap=True)
                yield Static(
                    "[dim]Drag to select · copy with terminal or Ctrl+Shift+C[/]",
                    id="trace-hint",
                    markup=True,
                )
        yield Footer()

    def _setup_panel_text(self) -> str:
        return format_setup_summary_rich(
            load_last_setup(),
            load_project_setup_summary(self.bridge.root),
        )

    def _tracker_text(self) -> str:
        if not self.bridge.ctx.is_initialized():
            return "[dim]Tracker:[/] initialize project with [bold]Setup keys[/] or /setup"
        from src.repl.plan_display import format_status_detail

        return format_status_detail(self.bridge.ctx)

    def _top_bar_text(self) -> str:
        from src.cli.model_picker import resolve_model_id

        reg = self.bridge.ctx.model_registry()
        raw = str(self.bridge.ctx.config.get("default_model", "—"))
        mid = resolve_model_id(raw, reg) or raw
        meta = reg.get_model(mid) or {}
        name = meta.get("display_name") or mid
        st = self.bridge.status_line()
        return (
            f"[bold #6cb6ff]{name}[/] [dim]({mid})[/]  "
            f"[dim]│[/]  {st}"
        )

    def _sync_model_select(self) -> None:
        from src.cli.model_picker import resolve_model_id

        sel = self.query_one("#model-select", Select)
        reg = self.bridge.ctx.model_registry()
        current = resolve_model_id(str(self.bridge.ctx.config.get("default_model", "")), reg)
        if not current:
            current = reg.list_models()[0] if reg.list_models() else ""
        options = select_options_for_widget(reg, current_id=current)
        if not options:
            return
        self._select_syncing = True
        try:
            sel.set_options(options)
            sel.value = current
            self._active_model_id = current
        except Exception:
            pass
        finally:
            self._select_syncing = False

    def _refresh_chrome(self, *, sync_select: bool = False) -> None:
        self.query_one("#top-bar", Static).update(self._top_bar_text())
        self.query_one("#tracker-panel", Static).update(self._tracker_text())
        self.query_one("#setup-panel", Static).update(self._setup_panel_text())
        if sync_select:
            self._sync_model_select()

    def _log_work(self, text: str) -> None:
        self.query_one("#activity-log", RichLog).write(f"[cyan]▸[/] [italic]{text}[/]")
        self.query_one("#activity-scroll", VerticalScroll).scroll_end(animate=False)

    def _apply_model_from_ui(self, model_id: str) -> None:
        from src.cli.model_picker import apply_model_choice, resolve_model_id

        reg = self.bridge.ctx.model_registry()
        mid = resolve_model_id(str(model_id), reg)
        if not mid or mid == self._active_model_id:
            return
        self._active_model_id = mid
        msg = apply_model_choice(self.bridge.ctx, mid)
        self._log(f"[green]✓[/] {msg}")
        self.query_one("#top-bar", Static).update(self._top_bar_text())
        self.query_one("#setup-panel", Static).update(self._setup_panel_text())

    def _log(self, text: str) -> None:
        self.query_one(RichLog).write(text)
        self._scroll_chat_end()

    def _scroll_chat_end(self) -> None:
        self.query_one("#chat-scroll", VerticalScroll).scroll_end(animate=False)

    def _log_user(self, text: str) -> None:
        self._last_user_prompt = text
        preview = text if len(text) <= 500 else text[:497] + "…"
        body = preview.replace("\n", "\n[bold white]  [/bold white]")
        self.query_one("#prompt-display", Static).update(
            f"[bold #6cb6ff]You[/]  {body}"
        )
        self._log(
            "\n[bold #6cb6ff]┏━ You ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n"
            f"[bold white]{body}[/]\n"
            "[bold #6cb6ff]┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n"
        )

    def _log_assistant(self, text: str) -> None:
        body = text.replace("\n", "\n[#79c0ff]│ [/#79c0ff]")
        self._log(
            "\n[bold #79c0ff]┏━ Assistant ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n"
            f"[#79c0ff]│ [/#79c0ff]{body}\n"
            "[bold #79c0ff]┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n"
        )

    def _log_system(self, text: str) -> None:
        self._log(f"[dim]· {text}[/]")

    def _set_chat_busy(self, busy: bool) -> None:
        self._chat_busy = busy
        composer = self.query_one("#composer", Horizontal)
        chat_input = self.query_one("#input", Input)
        if busy:
            composer.add_class("-busy")
            chat_input.disabled = True
            chat_input.placeholder = "Waiting for model… (Esc to cancel)"
        else:
            composer.remove_class("-busy")
            chat_input.disabled = False
            chat_input.placeholder = "Ask anything — slash commands optional"

    def _start_thinking(self) -> None:
        self._thinking_tick = 0
        self._tick_thinking()
        if self._thinking_timer is not None:
            self._thinking_timer.stop()
        self._thinking_timer = self.set_interval(0.35, self._tick_thinking)

    def _tick_thinking(self) -> None:
        frame = _THINK_FRAMES[self._thinking_tick % len(_THINK_FRAMES)]
        self._thinking_tick += 1
        self.query_one("#thinking-bar", Static).update(
            f"[bold #6cb6ff]{frame}[/] [italic]Thinking[/] "
            f"[dim]· scroll chat · Esc cancel[/]"
        )

    def _stop_thinking(self) -> None:
        if self._thinking_timer is not None:
            self._thinking_timer.stop()
            self._thinking_timer = None
        self.query_one("#thinking-bar", Static).update("")

    def _chat_sync(self, line: str) -> ChatJobResult:
        if not self._agent:
            return ChatJobResult("no_agent")
        try:
            reply = self._agent.chat(line)
            return ChatJobResult("ok", reply)
        except Exception as exc:
            return ChatJobResult("error", str(exc))

    def _begin_chat(self, line: str) -> None:
        self._set_chat_busy(True)
        self._log_work("Starting agent turn…")
        self._start_thinking()

        def run_chat() -> ChatJobResult:
            return self._chat_sync(line)

        # run_worker only accepts a zero-arg callable; do not pass line as 2nd positional
        # (Textual treats that as worker name — caused: missing argument 'line').
        self.run_worker(
            run_chat,
            thread=True,
            exclusive=True,
            group="chat",
            name="chat",
        )

    def on_mount(self) -> None:
        self._try_bind_last_project()
        self._active_model_id = str(self.bridge.ctx.config.get("default_model", ""))
        self._sync_model_select()
        log = self.query_one(RichLog)
        log.write("[bold #6cb6ff]Cognition Engine[/] ready")
        log.write(
            "[dim]Left panel:[/] [bold]Setup keys[/] · model dropdown · [bold]Change model[/] to search"
        )
        if self.bridge.ctx.is_initialized():
            log.write(f"[dim]Project:[/] {self.bridge.root}")
            goal = (self.bridge.ctx.get_project_goal() or "").strip()
            if goal:
                preview = goal if len(goal) <= 160 else goal[:157] + "…"
                log.write(f"[dim]Goal:[/] {preview}")
            log.write(
                "[dim]Session context:[/] /start then /bootstrap — not shown here by default"
            )
        else:
            last = load_last_setup().get("project_path")
            if last and Path(str(last)).expanduser().resolve() != self.bridge.root.resolve():
                log.write(
                    f"[yellow]No CE project in this folder.[/] [dim]Last project:[/] {last}\n"
                    f"[dim]Use[/] /project {last} [dim]or[/] cd there, then [bold]Setup keys[/]"
                )
            else:
                log.write("[yellow]Tip:[/] click [bold]Setup keys[/] or: cognition-engine setup")
        self._maybe_open_setup()

    def _maybe_open_setup(self) -> None:
        import os

        from src.cli.hermes_setup import needs_quick_setup

        if os.environ.get("CE_SKIP_SETUP") == "1":
            return
        if needs_quick_setup():
            self.call_after_refresh(self.action_open_setup)

    def action_open_setup(self) -> None:
        self.push_screen(QuickSetupScreen(self.bridge), self._on_setup_done)

    def _on_setup_done(self, saved: bool | None) -> None:
        import os

        if saved:
            os.environ["CE_SETUP_DONE"] = "1"
            self._active_model_id = str(self.bridge.ctx.config.get("default_model", ""))
            self._agent = self._build_agent()
            self._refresh_chrome(sync_select=True)
            self._log("[green]✓[/] Model and API key saved. You can chat now.")
        else:
            from src.cli.hermes_setup import needs_quick_setup

            if needs_quick_setup():
                self._log(
                    "[yellow]Setup skipped.[/] Click [bold]Setup keys[/] or export an API key "
                    "(e.g. ANTHROPIC_API_KEY). [dim]/keys[/] shows status."
                )

    @on(Select.Changed, "#model-select")
    def _on_model_dropdown(self, event: Select.Changed) -> None:
        if self._select_syncing:
            return
        self._apply_model_from_ui(event.value)  # type: ignore[arg-type]

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
        elif bid == "btn-show-plan":
            self._run_bridge(lambda: self.bridge.cmd_show_plan())
        elif bid == "btn-end":
            if self._require_project("End session"):
                self.action_prompt_end()
        elif bid == "btn-commit":
            if self._require_project("Git commit"):
                self._prompt_commit()
        elif bid == "btn-setup":
            self.action_open_setup()
        elif bid == "btn-quit":
            self.action_confirm_quit()

    def _bridge_call(self, fn: Any) -> str:
        try:
            result = fn()
            return str(result) if result else ""
        except Exception as exc:
            from src.core.exceptions import DNALoadError

            if isinstance(exc, DNALoadError):
                return f"__DNA__:{exc}"
            return f"__ERR__:{exc}"

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.worker.group == "bridge":
            if event.state == WorkerState.SUCCESS:
                out = str(event.worker.result or "")
                if out.startswith("__DNA__:"):
                    self._require_project("This command")
                elif out.startswith("__ERR__:"):
                    self._log_system(out[7:])
                elif out and "MASTER PLAN" in out:
                    self._log(out)
                elif out:
                    self._log_system(out)
                self._refresh_chrome(sync_select=False)
            elif event.state == WorkerState.ERROR:
                self._log_system(str(event.worker.error))
            return
        if event.worker.group != "chat":
            return
        if event.state not in (WorkerState.SUCCESS, WorkerState.ERROR, WorkerState.CANCELLED):
            return
        self._stop_thinking()
        self._set_chat_busy(False)
        if event.state == WorkerState.CANCELLED:
            self._log_system("Request cancelled.")
            self.query_one("#input", Input).focus()
            return
        if event.state == WorkerState.ERROR:
            err = event.worker.error
            self._log_assistant(f"[red]Error[/]\n{err}")
            self.query_one("#input", Input).focus()
            return
        result: ChatJobResult = event.worker.result
        if result.kind == "ok":
            self._log_assistant(result.payload)
        elif result.kind == "error":
            self._log_assistant(f"[red]{result.payload}[/]")
        elif result.kind == "no_agent":
            self._log_system(
                "Chat needs an API key. Click [bold]Setup keys[/] or type /keys"
            )
        self._refresh_chrome(sync_select=False)
        self.query_one("#input", Input).focus()
        self._scroll_chat_end()

    def _run_bridge(self, fn) -> None:
        def run_bridge() -> str:
            return self._bridge_call(fn)

        self.run_worker(
            run_bridge,
            thread=True,
            group="bridge",
            name="bridge",
        )

    def _cancel_chat_workers(self) -> None:
        for worker in self.workers:
            if worker.group == "chat" and worker.state == WorkerState.RUNNING:
                worker.cancel()

    def action_confirm_quit(self) -> None:
        self.push_screen(ConfirmQuitScreen(), self._on_quit_confirmed)

    def _on_quit_confirmed(self, ok: bool | None) -> None:
        if ok:
            self.exit()

    def action_handle_escape(self) -> None:
        if self._chat_busy:
            self._cancel_chat_workers()
            return
        self.action_confirm_quit()

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
        self._apply_model_from_ui(model_id)
        self._select_syncing = True
        try:
            sel = self.query_one("#model-select", Select)
            sel.value = self._active_model_id
        except Exception:
            pass
        finally:
            self._select_syncing = False

    def action_clear_log(self) -> None:
        self.query_one(RichLog).clear()

    def action_scroll_up(self) -> None:
        self.query_one("#chat-scroll", VerticalScroll).scroll_up(animate=False)

    def action_scroll_down(self) -> None:
        self.query_one("#chat-scroll", VerticalScroll).scroll_down(animate=False)

    def action_request_quit(self) -> None:
        self.action_confirm_quit()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._chat_busy:
            return
        line = event.value.strip()
        event.input.value = ""
        if not line:
            return

        if line.startswith("/"):
            cmd = line.split(maxsplit=1)[0].lower()
            if cmd in ("/exit", "/quit"):
                self.action_confirm_quit()
                return
            if cmd in ("/model", "/models") and cmd == "/model" and line.strip().lower() == "/model":
                self.action_pick_model()
                return
            if cmd == "/setup":
                self.action_open_setup()
                return
            if cmd in ("/showplan", "/show-plan"):
                self._run_bridge(lambda: self.bridge.cmd_show_plan())
                return
            self._log_user(line)
            result = self.bridge.dispatch(line)
            if result == "__EXIT__":
                self.action_confirm_quit()
                return
            if line.split(maxsplit=1)[0].lower() in ("/project", "/cd"):
                self._agent = self._build_agent()
            if result:
                if cmd == "/models":
                    self._log(format_models_table(self.bridge.ctx.model_registry()))
                elif cmd == "/plan" or "MASTER PLAN" in result:
                    self._log(result)
                elif cmd == "/status":
                    self._log(result)
                    self._refresh_chrome(sync_select=False)
                else:
                    self._log_system(result)
            self._refresh_chrome(sync_select=False)
            return

        self._log_user(line)
        if self._agent:
            self._begin_chat(line)
        else:
            self._log_system(
                "Chat needs an API key. Click [bold]Setup keys[/] or type /keys"
            )
