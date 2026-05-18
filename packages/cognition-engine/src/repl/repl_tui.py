"""Advanced Textual TUI — persistent commands, dropdown model select, searchable picker."""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from textual import events, on
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
    LoadingIndicator,
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
from src.repl.chat_log import ChatRichLog
from src.repl.agent_tasks import TaskBoard, ingest_activity, task_board_markup
from src.repl.clipboard_util import save_copy_fallback
from src.repl.response_clean import clean_assistant_text
from src.repl.repl_theme import CE_APP_CSS, CE_BRAND_MARKUP, ChromeStatic, PaneScroll
from src.repl.session_bridge import SLASH_COMMANDS, SessionBridge
from src.repl.markup_safe import escape_markup
from src.repl.live_thinking import LiveAgentView, live_thinking_markup
from src.repl.rail_sidebar import format_left_rail
from src.repl.thinking_anim import thinking_panel_markup
from src.repl.tips import CE_TIPS
from src.repl.welcome import welcome_markup
from src.repl.trace_viz import trace_lane_markup
from src.agent.permissions import PermissionDecision


COMMAND_BUTTONS: list[tuple[str, str, str]] = [
    ("btn-start", "Start session", "primary"),
    ("btn-plan", "Generate plan", "primary"),
    ("btn-show-plan", "Show plan", "primary"),
    ("btn-shield", "Shield info", ""),
    ("btn-status", "Track progress", ""),
    ("btn-end", "End session", ""),
    ("btn-setup", "Setup keys", "primary"),
    ("btn-quit", "Exit CE", "danger"),
]

COMMAND_HINTS = (
    "[dim]Ctrl+M[/] model search · [dim]PgUp[/]/[dim]Dn[/] scroll · "
    "[dim]Click chat log[/] then drag to select"
)


@dataclass(frozen=True)
class ChatJobResult:
    kind: str
    payload: str = ""


class ConfirmQuitScreen(ModalScreen[bool]):
    """Confirm before closing the agent console."""

    def compose(self) -> ComposeResult:
        with Vertical(id="quit-frame"):
            yield ChromeStatic("[bold #f85149]Exit Cognition Engine?[/]", id="quit-title")
            yield ChromeStatic("[dim]Unsaved chat is kept in this session only.[/dim]", markup=True)
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


@dataclass(frozen=True)
class _PermissionAnswer:
    allowed: bool
    remember_session: bool


class AgentPermissionScreen(ModalScreen[_PermissionAnswer | None]):
    """User approval for destructive agent actions."""

    def __init__(self, category: str, detail: str) -> None:
        super().__init__()
        self._category = category
        self._detail = detail

    def compose(self) -> ComposeResult:
        safe = escape_markup(self._detail)
        with Vertical(id="perm-frame"):
            yield ChromeStatic(
                f"[bold #e3b341]Allow {escape_markup(self._category)}?[/]",
                id="perm-title",
            )
            yield ChromeStatic(safe, id="perm-detail")
            yield ChromeStatic(
                "[dim]Session = no more prompts for this type until /end[/]",
                markup=True,
            )
            with Horizontal(id="perm-actions"):
                yield Button("Allow for session", id="perm-session", variant="warning")
                yield Button("Allow once", id="perm-once", variant="primary")
                yield Button("Deny", id="perm-deny", variant="error")

    @on(Button.Pressed, "#perm-session")
    def _session(self, _event: Button.Pressed) -> None:
        self.dismiss(_PermissionAnswer(True, True))

    @on(Button.Pressed, "#perm-once")
    def _once(self, _event: Button.Pressed) -> None:
        self.dismiss(_PermissionAnswer(True, False))

    @on(Button.Pressed, "#perm-deny")
    def _deny(self, _event: Button.Pressed) -> None:
        self.dismiss(_PermissionAnswer(False, False))

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(_PermissionAnswer(False, False))


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
            yield ChromeStatic(
                f"[bold #6cb6ff]Choose model[/]  [dim]active: {current}[/]",
                id="picker-title",
            )
            yield Input(placeholder="Search by name, id, or provider…", id="picker-search")
            yield ListView(id="picker-list")
            yield ChromeStatic(
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
            yield ChromeStatic("[bold #6cb6ff]Setup — model & API key[/]", id="setup-title")
            yield ChromeStatic("", id="setup-model-line", markup=True)
            yield Button("Choose model…", id="setup-pick-model")
            yield ChromeStatic("", id="setup-provider-hint", markup=True)
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
        from src.cli.api_key_providers import env_var_for_model, provider_label_for_model
        from src.cli.model_picker import resolve_model_id

        reg = self.bridge.ctx.model_registry()
        mid = resolve_model_id(self._model_id, reg) or self._model_id or "claude-haiku-20240307"
        self._model_id = mid
        meta = reg.get_model(mid) or {}
        name = meta.get("display_name") or mid
        label = provider_label_for_model(mid)
        env_var = env_var_for_model(mid)
        self.query_one("#setup-model-line", Static).update(
            f"Model: [cyan]{name}[/] [dim]({mid})[/]"
        )
        self.query_one("#setup-provider-hint", Static).update(
            f"[dim]API key for [bold]{label}[/] · export {env_var}[/]"
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
        from src.cli.baral_setup import persist_setup_choices

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


class ComposerInput(Input):
    """Bottom prompt — not part of a log-to-log mouse selection rectangle."""

    ALLOW_SELECT = False


class CognitionReplApp(App):
    """Professional agent console — no /help required."""

    ALLOW_SELECT = True

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
        Binding("pageup", "scroll_up", "▲", show=False, priority=True),
        Binding("pagedown", "scroll_down", "▼", show=False, priority=True),
    ]

    def __init__(self, project_root: Path | None = None) -> None:
        super().__init__()
        root = project_root or resolve_project_root()
        self.bridge = SessionBridge(root)
        self._agent = self._build_agent()
        self._select_syncing = False
        self._active_model_id = str(self.bridge.ctx.config.get("default_model", ""))
        self._thinking_timer: Timer | None = None
        self._tips_timer: Timer | None = None
        self._thinking_tick = 0
        self._tip_index = 0
        self._chat_busy = False
        self._last_user_prompt = ""
        self._live_tokens: dict[str, int] = {
            "input": 0,
            "output": 0,
            "total": 0,
            "last_turn": 0,
        }
        self._last_assistant_plain = ""
        self._typing_timer: Timer | None = None
        self._typing_full = ""
        self._typing_pos = 0
        self._typing_pulse = 0
        self._thinking_min_until = 0.0
        self._last_activity = "Ready"
        self._activity_recent: list[str] = []
        self._live_view = LiveAgentView(max_steps=40)
        self._task_board = TaskBoard()
        self._stream_flush_at = 0.0
        self._token_refresh_timer: Timer | None = None

    def _build_agent(self):
        try:
            from src.agent.orchestrator import AgentOrchestrator

            return AgentOrchestrator(
                self.bridge.ctx,
                on_activity=self._on_agent_activity,
                on_tokens=self._on_agent_tokens,
                on_permission=self._request_agent_permission,
                on_stream=self._on_agent_stream,
            )
        except Exception:
            return None

    def _request_agent_permission(self, category: str, detail: str) -> PermissionDecision:
        result: list[PermissionDecision] = [PermissionDecision(False)]
        done = threading.Event()

        def finish(answer: _PermissionAnswer | None) -> None:
            if answer and answer.allowed:
                result[0] = PermissionDecision(
                    allowed=True,
                    remember_session=answer.remember_session,
                )
            done.set()

        def open_modal() -> None:
            self.push_screen(AgentPermissionScreen(category, detail), finish)

        try:
            self.call_from_thread(open_modal)
        except RuntimeError:
            open_modal()
        done.wait(timeout=600)
        if not done.is_set():
            return PermissionDecision(False)
        return result[0]

    def _on_agent_activity(self, msg: str) -> None:
        try:
            self.call_from_thread(self._apply_activity, msg)
        except RuntimeError:
            self._apply_activity(msg)

    def _apply_activity(self, msg: str) -> None:
        self._last_activity = msg
        self._activity_recent.append(msg)
        if len(self._activity_recent) > 80:
            self._activity_recent = self._activity_recent[-80:]
        self._live_view.status = msg
        self._live_view.trace = list(self._activity_recent)
        ingest_activity(self._task_board, msg)
        lower = msg.lower()
        if "model step" in lower:
            self._live_view.stream = ""
            self._typing_pos = 0
            self._live_view.planned = []
            sm = re.search(r"step\s+(\d+)\s*/\s*(\d+)", lower)
            if sm:
                self._live_view.step = int(sm.group(1))
                self._live_view.max_steps = int(sm.group(2))
        if "▸ next action:" in lower:
            plan = msg.split(":", 1)[-1].strip()
            if plan and (not self._live_view.planned or self._live_view.planned[-1] != plan):
                self._live_view.planned.append(plan)
        self._log_work(msg)
        if self._chat_busy:
            safe = escape_markup(msg)
            self._log(f"[dim #8b949e]⚙ {safe}[/]")
        if self._chat_busy:
            self._update_thinking_box()

    def _on_agent_stream(self, chunk: str) -> None:
        if not chunk:
            return
        try:
            self.call_from_thread(self._apply_stream, chunk)
        except RuntimeError:
            self._apply_stream(chunk)

    def _apply_stream(self, chunk: str) -> None:
        if "dsml" in chunk.lower() or "<|" in chunk:
            return
        self._live_view.stream += chunk
        if len(self._live_view.stream) > 4000:
            self._live_view.stream = self._live_view.stream[-4000:]
        now = time.monotonic()
        if now - self._stream_flush_at < 0.06:
            return
        self._stream_flush_at = now
        self._update_thinking_box()

    def _on_agent_tokens(self, usage: dict[str, int]) -> None:
        try:
            self.call_from_thread(self._apply_token_usage, usage)
        except RuntimeError:
            self._apply_token_usage(usage)
        self._refresh_token_bar()

    def _apply_token_usage(self, usage: dict[str, int]) -> None:
        self._live_tokens = {
            "input": int(usage.get("input", 0)),
            "output": int(usage.get("output", 0)),
            "total": int(usage.get("total", 0)),
            "last_turn": int(usage.get("last_turn", 0)),
        }
        self._refresh_token_bar()

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
            with PaneScroll(id="left-rail", can_focus=True):
                with Vertical(id="left-rail-inner"):
                    yield ChromeStatic(
                        format_left_rail(
                            project_root=self.bridge.root,
                            setup=load_last_setup(),
                            project_setup=load_project_setup_summary(self.bridge.root),
                            ctx=self.bridge.ctx,
                        ),
                        id="sidebar-status",
                        markup=True,
                    )
                    yield ChromeStatic("ACTIONS", classes="rail-section-title")
                    with Vertical(id="command-buttons"):
                        for bid, label, variant in COMMAND_BUTTONS:
                            classes = ""
                            if variant == "primary":
                                classes = "-primary"
                            elif variant == "danger":
                                classes = "-danger"
                            yield Button(label, id=bid, classes=classes)
                    yield ChromeStatic(COMMAND_HINTS, id="command-hints", markup=True)
            with Vertical(id="chat-column"):
                with Horizontal(id="header-strip"):
                    yield Select(
                        model_options,
                        id="model-select",
                        prompt="▼ Choose model",
                        value=model_value,
                    )
                    yield ChromeStatic(
                        self._header_meta_text(),
                        id="header-meta",
                        markup=True,
                    )
                with Vertical(id="chat-body"):
                    yield ChatRichLog(
                        id="log",
                        highlight=True,
                        markup=True,
                        wrap=True,
                        auto_scroll=True,
                        min_width=20,
                    )
                with Vertical(id="thinking-box"):
                    with Horizontal(id="thinking-head"):
                        yield LoadingIndicator(id="think-spinner")
                        yield ChromeStatic("", id="chat-thinking", markup=True)
                    yield ChromeStatic("", id="task-list", markup=True)
                    yield ChromeStatic("", id="thinking-detail", markup=True)
                with Vertical(id="composer-stack"):
                    with Horizontal(id="composer"):
                        yield ChromeStatic("❯", id="prompt-glyph")
                        yield ComposerInput(
                            placeholder="Ask anything — type / for commands",
                            id="input",
                        )
                    yield ChromeStatic("", id="slash-suggest", markup=True, classes="hidden")
            with Vertical(id="trace-rail"):
                yield ChromeStatic("AGENT TRACE", classes="rail-section-title")
                with Vertical(id="trace-body"):
                    yield ChatRichLog(
                        id="activity-log",
                        highlight=True,
                        markup=True,
                        wrap=True,
                        auto_scroll=True,
                        min_width=1,
                    )
                yield ChromeStatic(
                    "[dim]Click the log, then drag to select text · "
                    "Shift+drag if selection does not start · "
                    "terminal copy:[/] [dim]CE_NATIVE_COPY=1[/]",
                    id="trace-hint",
                    markup=True,
                )
        yield ChromeStatic(self._tip_text(), id="tips-bar", markup=True)
        yield Footer()

    def _setup_panel_text(self) -> str:
        return format_setup_summary_rich(
            load_last_setup(),
            load_project_setup_summary(self.bridge.root),
            ctx=self.bridge.ctx,
        )

    def _tracker_text(self) -> str:
        if not self.bridge.ctx.is_initialized():
            return "[dim]Tracker:[/] initialize project with [bold]Setup keys[/] or /setup"
        from src.repl.plan_display import format_status_detail

        return format_status_detail(self.bridge.ctx)

    def _session_token_totals(self) -> dict[str, int]:
        t = dict(self._live_tokens)
        if self._agent:
            t = {
                "input": int(self._agent.session_tokens.get("input", 0)),
                "output": int(self._agent.session_tokens.get("output", 0)),
                "total": int(self._agent.session_tokens.get("total", 0)),
                "last_turn": int(self._agent.session_tokens.get("last_turn", 0)),
            }
        if self.bridge.ctx.is_initialized():
            try:
                op = self.bridge.ctx.active_operational_memory()
                totals = op.get_session_summary().get("tokens") or {}
                if int(totals.get("total", 0)) >= t["total"]:
                    t = {
                        "input": int(totals.get("input", 0)),
                        "output": int(totals.get("output", 0)),
                        "total": int(totals.get("total", 0)),
                        "last_turn": t.get("last_turn", 0),
                    }
            except Exception:
                pass
        return t

    def _header_meta_text(self) -> str:
        proj = self.bridge.root.name or str(self.bridge.root)
        init = "[#3fb950]●[/]" if self.bridge.ctx.is_initialized() else "[#768390]○[/]"
        t = self._session_token_totals()
        return (
            f"{init} [white]{proj}[/]  "
            f"[#e3b341]{t['total']:,}[/] tok [dim]↑{t['input']:,} ↓{t['output']:,}[/]"
        )

    def _token_bar_text(self) -> str:
        t = self._session_token_totals()
        last = f"  [dim]last turn[/] [bold]+{t['last_turn']:,}[/]" if t["last_turn"] else ""
        return (
            f"[bold #e3b341]⚡ Tokens[/]  [white]{t['total']:,}[/] total  "
            f"[dim]↑[/][#79c0ff]{t['input']:,}[/] in  "
            f"[dim]↓[/][#a5d6ff]{t['output']:,}[/] out[/]"
            f"{last}"
        )

    def _refresh_token_bar(self) -> None:
        try:
            self.query_one("#header-meta", Static).update(self._header_meta_text())
        except Exception:
            pass

    def _update_thinking_box(self) -> None:
        try:
            self.query_one("#task-list", Static).update(
                task_board_markup(self._task_board, title="Agent")
            )
            if self._chat_busy and self._typing_timer is not None:
                if (self._live_view.stream or "").strip() or self._typing_pos > 0:
                    return
            _, detail = live_thinking_markup(self._thinking_tick, self._live_view)
            self.query_one("#thinking-detail", Static).update(detail)
        except Exception:
            pass

    def _tip_text(self) -> str:
        n = len(CE_TIPS)
        tip_a = CE_TIPS[self._tip_index % n]
        tip_b = CE_TIPS[(self._tip_index + n // 2) % n]
        return f"[bold #6cb6ff]Tip[/]  {tip_a}\n[bold #6cb6ff]    [/]  [dim]{tip_b}[/]"

    def _tick_tip(self) -> None:
        self._tip_index += 2
        try:
            self.query_one("#tips-bar", Static).update(self._tip_text())
        except Exception:
            pass

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
        try:
            self.query_one("#header-meta", Static).update(self._header_meta_text())
            self._sync_model_select()
            self.query_one("#sidebar-status", Static).update(
                format_left_rail(
                    project_root=self.bridge.root,
                    setup=load_last_setup(),
                    project_setup=load_project_setup_summary(self.bridge.root),
                    ctx=self.bridge.ctx,
                )
            )
        except Exception:
            pass
        self._refresh_token_bar()
        if sync_select:
            self._sync_model_select()

    def _log_work(self, text: str) -> None:
        self.query_one("#activity-log", ChatRichLog).write(trace_lane_markup(text))
        self.query_one("#activity-log", ChatRichLog).scroll_end(animate=False)

    def _apply_model_from_ui(self, model_id: str) -> None:
        from src.cli.model_picker import apply_model_choice, resolve_model_id

        reg = self.bridge.ctx.model_registry()
        mid = resolve_model_id(str(model_id), reg)
        if not mid or mid == self._active_model_id:
            return
        self._active_model_id = mid
        msg = apply_model_choice(self.bridge.ctx, mid)
        self._agent = self._build_agent()
        self._log(f"[green]✓[/] {msg}")
        self._refresh_chrome(sync_select=False)

    def _log(self, text: str) -> None:
        self.query_one("#log", ChatRichLog).write(text)
        self._scroll_chat_end()

    def _scroll_chat_end(self) -> None:
        self.query_one("#log", ChatRichLog).scroll_end(animate=False)

    def _log_user(self, text: str) -> None:
        self._last_user_prompt = text
        preview = text if len(text) <= 120 else text[:117] + "…"
        body = escape_markup(preview)
        self._log(
            "\n[bold #6cb6ff]┏━ You ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n"
            f"[bold white]{body}[/]\n"
            "[bold #6cb6ff]┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n"
        )

    def _log_assistant(self, text: str) -> None:
        clean = clean_assistant_text(text)
        self._last_assistant_plain = clean or text
        if self._last_assistant_plain.strip():
            save_copy_fallback(self._last_assistant_plain)
        body = escape_markup(self._last_assistant_plain).replace(
            "\n", "\n[#79c0ff]│ [/#79c0ff]"
        )
        self._log(
            "\n[bold #79c0ff]┏━ Assistant ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n"
            f"[#79c0ff]│ [/#79c0ff]{body}\n"
            "[bold #79c0ff]┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/]\n"
        )

    def _clear_chat_thinking(self) -> None:
        try:
            self.query_one("#thinking-detail", Static).update("")
        except Exception:
            pass

    def _log_assistant_typing(self, text: str) -> None:
        """Reveal assistant reply character-by-character (Claude Code–style)."""
        clean = clean_assistant_text(text)
        self._last_assistant_plain = clean or text
        self._typing_full = self._last_assistant_plain
        self._typing_pos = 0
        try:
            self.query_one("#thinking-box", Vertical).add_class("visible")
        except Exception:
            pass
        if self._typing_timer is not None:
            self._typing_timer.stop()
        self._typing_timer = self.set_interval(0.018, self._typing_tick)

    def _typing_tick(self) -> None:
        if self._chat_busy:
            src = self._live_view.stream
            low = src.lower()
            if "dsml" in low or "<|" in src:
                return
            if not src.strip():
                self._typing_pulse += 1
                dots = "·" * (self._typing_pulse % 4)
                try:
                    self.query_one("#thinking-detail", Static).update(
                        "[bold #58a6ff]╭─ Response ─────────────────────╮[/]\n"
                        f"[bold #58a6ff]│[/] [dim]{dots}[/][#79c0ff]▌[/]\n"
                        "[bold #58a6ff]╰────────────────────────────────╯[/]"
                    )
                except Exception:
                    pass
                return
            step = max(2, min(80, max(len(src) // 20, 4)))
            self._typing_pos = min(len(src), self._typing_pos + step)
            partial = src[: self._typing_pos]
            display = escape_markup(partial.replace("\n", " "))
            if len(display) > 220:
                display = "…" + display[-220:]
            try:
                self.query_one("#thinking-detail", Static).update(
                    f"[bold #58a6ff]╭─ Response (streaming) ─────────╮[/]\n"
                    f"[bold #58a6ff]│[/] [#79c0ff]{display}[/][bold #79c0ff]▌[/]\n"
                    f"[bold #58a6ff]╰────────────────────────────────╯[/]"
                )
                self.query_one("#log", ChatRichLog).scroll_end(animate=False)
            except Exception:
                pass
            return
        if not self._typing_full:
            if self._typing_timer is not None:
                self._typing_timer.stop()
                self._typing_timer = None
            return
        if self._typing_pos >= len(self._typing_full):
            if self._typing_timer is not None:
                self._typing_timer.stop()
                self._typing_timer = None
            self._hide_thinking_ui()
            self._log_assistant(self._typing_full)
            return
        step = max(2, len(self._typing_full) // 120)
        end = min(self._typing_pos + step, len(self._typing_full))
        self._typing_pos = end
        partial = self._typing_full[:end]
        display = escape_markup(partial.replace("\n", " "))
        if len(display) > 200:
            display = "…" + display[-200:]
        self.query_one("#thinking-detail", Static).update(
            f"[bold #58a6ff]╭─ Response ─────────────────────╮[/]\n"
            f"[bold #58a6ff]│[/] [#79c0ff]{display}[/][bold #79c0ff]▌[/]\n"
            f"[bold #58a6ff]╰────────────────────────────────╯[/]"
        )
        self.query_one("#log", ChatRichLog).scroll_end(animate=False)

    def _log_system(self, text: str) -> None:
        self._log(f"[dim]· {text}[/]")

    def _display_plan(self, *, generate: bool = False) -> None:
        """Show plan in main chat immediately (sync — reliable visibility)."""
        if not self.bridge.ctx.is_initialized():
            self._require_project("Show plan")
            return
        self._log_work("Loading master plan…")
        try:
            if generate:
                goal = self.bridge.ctx.get_project_goal()
                if not goal:
                    self._log("[yellow]Set a goal first:[/] /goal Your project objective")
                    return
                text = self.bridge.cmd_plan("")
            else:
                text = self.bridge.cmd_show_plan()
            if not text or "No plan yet" in text:
                self._log_system(text or "No plan in DNA.")
                return
            self._log(
                "\n[bold #3fb950]══════════════════════════════════════[/]\n"
                f"{text}\n"
                "[bold #3fb950]══════════════════════════════════════[/]\n"
            )
            self._refresh_chrome(sync_select=False)
        except Exception as exc:
            self._log_system(f"Plan error: {exc}")

    def _set_chat_busy(self, busy: bool) -> None:
        self._chat_busy = busy
        composer = self.query_one("#composer", Horizontal)
        chat_input = self.query_one("#input", Input)
        if busy:
            composer.add_class("-busy")
            chat_input.disabled = True
            chat_input.placeholder = "Working… Esc to cancel"
        else:
            composer.remove_class("-busy")
            chat_input.disabled = False
            chat_input.placeholder = "Ask anything — type / for commands"

    def _collapse_agent_progress(self) -> None:
        try:
            box = self.query_one("#thinking-box", Vertical)
            box.remove_class("visible")
            self.query_one("#task-list", Static).update("")
            self.query_one("#thinking-detail", Static).update("")
        except Exception:
            pass

    def _start_thinking(self) -> None:
        self._thinking_tick = 0
        self._activity_recent = []
        self._live_view = LiveAgentView(max_steps=40)
        self._task_board = TaskBoard()
        self._stream_flush_at = 0.0
        self._thinking_min_until = time.monotonic() + 1.2
        self.query_one("#thinking-box", Vertical).add_class("visible")
        self._typing_pulse = 0
        self._show_streaming_placeholder_frame()
        self._update_thinking_box()
        if self._thinking_timer is not None:
            self._thinking_timer.stop()
        self._thinking_timer = self.set_interval(0.1, self._tick_thinking)
        self._typing_pos = 0
        if self._typing_timer is not None:
            self._typing_timer.stop()
        self._typing_timer = self.set_interval(0.016, self._typing_tick)

    def _show_streaming_placeholder_frame(self) -> None:
        """First paint before any model tokens — instant feedback after Enter."""
        try:
            self.query_one("#thinking-detail", Static).update(
                "[bold #58a6ff]╭─ Response ─────────────────────╮[/]\n"
                "[bold #58a6ff]│[/] [#79c0ff]▌[/]\n"
                "[bold #58a6ff]╰────────────────────────────────╯[/]"
            )
        except Exception:
            pass

    def _tick_thinking(self) -> None:
        self._thinking_tick += 1
        self._update_thinking_box()

    def _stop_agent_thinking_only(self) -> None:
        """Stop the agent spinner timer only; keep thinking box for reply typing."""
        if self._thinking_timer is not None:
            self._thinking_timer.stop()
            self._thinking_timer = None

    def _hide_thinking_ui(self) -> None:
        if self._thinking_timer is not None:
            self._thinking_timer.stop()
            self._thinking_timer = None
        self._collapse_agent_progress()
        if not self._typing_timer:
            self._clear_chat_thinking()

    def _stop_thinking(self) -> None:
        if time.monotonic() < self._thinking_min_until:
            delay = self._thinking_min_until - time.monotonic()
            self.set_timer(delay, self._hide_thinking_ui)
            return
        self._hide_thinking_ui()

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
        self._activity_recent = []
        self._start_thinking()
        self._log_work("Starting agent turn…")
        self._log(
            "[dim #8b949e]Agentic mode — tools run live (see right panel + lines below).[/]"
        )

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

    def _migrate_and_reload_keys(self) -> None:
        from src.cli.baral_setup import _load_global, _persist_migrated_keys

        data = _load_global()
        if data:
            _persist_migrated_keys(data)
            self.bridge.ctx.config.reload()

    def on_mount(self) -> None:
        self._migrate_and_reload_keys()
        self._try_bind_last_project()
        self._active_model_id = str(self.bridge.ctx.config.get("default_model", ""))
        self._sync_model_select()
        self._tips_timer = self.set_interval(8.0, self._tick_tip)
        self._token_refresh_timer = self.set_interval(1.5, self._refresh_token_bar)
        try:
            self.query_one("#header-meta", Static).update(self._header_meta_text())
        except Exception:
            pass
        try:
            self._collapse_agent_progress()
        except Exception:
            pass
        log = self.query_one("#log", ChatRichLog)
        goal = ""
        if self.bridge.ctx.is_initialized():
            goal = (self.bridge.ctx.get_project_goal() or "").strip()
        log.write(
            welcome_markup(
                project_root=str(self.bridge.root),
                initialized=self.bridge.ctx.is_initialized(),
                goal=goal,
            )
        )
        self.query_one("#input", Input).focus()
        if not self.bridge.ctx.is_initialized():
            last = load_last_setup().get("project_path")
            if last and Path(str(last)).expanduser().resolve() != self.bridge.root.resolve():
                log.write(
                    f"\n[yellow]No CE project in this folder.[/] [dim]Last project:[/] {last}\n"
                    f"[dim]Use[/] /project {last} [dim]or[/] cd there, then [bold]Setup keys[/]"
                )
            else:
                log.write(
                    "\n[yellow]Not initialized here.[/] Sidebar [bold]Setup keys[/] "
                    "or: [dim]cognition-engine setup --project .[/]"
                )
        self._maybe_open_setup()

    def _maybe_open_setup(self) -> None:
        import os

        from src.cli.baral_setup import needs_quick_setup

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
            self._migrate_and_reload_keys()
            self._active_model_id = str(self.bridge.ctx.config.get("default_model", ""))
            self._agent = self._build_agent()
            self._refresh_chrome(sync_select=True)
            self._log("[green]✓[/] Model and API key saved. You can chat now.")
        else:
            from src.cli.baral_setup import needs_quick_setup

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
            self._display_plan(generate=False)
        elif bid == "btn-shield":
            self._log(self.bridge.cmd_shield())
        elif bid == "btn-end":
            if self._require_project("End session"):
                self.action_prompt_end()
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
        self._stop_agent_thinking_only()
        if event.state == WorkerState.CANCELLED:
            if self._typing_timer is not None:
                self._typing_timer.stop()
                self._typing_timer = None
            self._set_chat_busy(False)
            self._hide_thinking_ui()
            self._log_system("Request cancelled.")
            self.query_one("#input", Input).focus()
            return
        if event.state == WorkerState.ERROR:
            if self._typing_timer is not None:
                self._typing_timer.stop()
                self._typing_timer = None
            self._set_chat_busy(False)
            self._hide_thinking_ui()
            err = event.worker.error
            self._log_assistant(f"[red]Error[/]\n{err}")
            self.query_one("#input", Input).focus()
            return
        result: ChatJobResult = event.worker.result
        if self._typing_timer is not None:
            self._typing_timer.stop()
            self._typing_timer = None
        self._set_chat_busy(False)
        if result.kind == "ok":
            p = result.payload or ""
            clean = clean_assistant_text(p) or p.strip()
            self._last_assistant_plain = clean or p
            if (self._last_assistant_plain or "").strip():
                save_copy_fallback(self._last_assistant_plain)
            streamed = bool((self._live_view.stream or "").strip())
            if streamed and (self._last_assistant_plain or "").strip():
                self._log_assistant(self._last_assistant_plain)
                self._hide_thinking_ui()
            elif (self._last_assistant_plain or "").strip():
                self._log_assistant_typing(p)
            else:
                self._hide_thinking_ui()
                self._log_system("(empty reply)")
        elif result.kind == "error":
            self._log_assistant_typing(f"[red]{result.payload}[/]")
        elif result.kind == "no_agent":
            self._hide_thinking_ui()
            self._log_system(
                "Chat needs an API key. Click [bold]Setup keys[/] or type /keys"
            )
        if self._agent:
            self._apply_token_usage(dict(self._agent.session_tokens))
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
        if self.bridge.ctx.get_project_goal():
            self._display_plan(generate=True)
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

    def _slash_matches(self, value: str) -> list[str]:
        if not value.lstrip().startswith("/"):
            return []
        tok = value.lstrip().split(maxsplit=1)[0].lower()
        return [c for c in SLASH_COMMANDS if c.startswith(tok)][:18]

    def _refresh_slash_suggest(self, value: str) -> None:
        try:
            sug = self.query_one("#slash-suggest", ChromeStatic)
        except Exception:
            return
        m = self._slash_matches(value)
        if not m:
            sug.add_class("hidden")
            sug.update("")
            return
        sug.remove_class("hidden")
        sug.update("[dim]" + "   ".join(m) + "[/]")

    @on(Input.Changed, "#input")
    def _on_input_prompt_changed(self, event: Input.Changed) -> None:
        self._refresh_slash_suggest(event.value)

    def on_key(self, event: events.Key) -> None:
        if event.key != "tab":
            return
        w = self.focused
        if w is None or getattr(w, "id", None) != "input":
            return
        inp = self.query_one("#input", Input)
        m = self._slash_matches(inp.value)
        if not m:
            return
        prefix = inp.value.split(maxsplit=1)[0] if inp.value.strip() else "/"
        if not prefix.startswith("/"):
            return
        pick = m[0]
        tail = inp.value[len(prefix) :]
        inp.value = pick + tail
        plen = len(pick)
        inp.cursor_position = plen if tail else min(plen + 1, len(inp.value))
        self._refresh_slash_suggest(inp.value)
        event.stop()

    def action_clear_log(self) -> None:
        self.query_one("#log", ChatRichLog).clear()

    def _scroll_target(self) -> VerticalScroll | PaneScroll | ChatRichLog:
        w = self.focused
        if isinstance(w, (VerticalScroll, PaneScroll)):
            return w
        if isinstance(w, ChatRichLog):
            return w
        if w is not None:
            parent = getattr(w, "parent", None)
            while parent is not None:
                if isinstance(parent, (VerticalScroll, PaneScroll)):
                    return parent
                if isinstance(parent, ChatRichLog):
                    return parent
                parent = getattr(parent, "parent", None)
        return self.query_one("#log", ChatRichLog)

    def action_scroll_up(self) -> None:
        self._scroll_target().scroll_up(animate=False)

    def action_scroll_down(self) -> None:
        self._scroll_target().scroll_down(animate=False)

    def action_request_quit(self) -> None:
        self.action_confirm_quit()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        try:
            self.query_one("#slash-suggest", ChromeStatic).add_class("hidden")
        except Exception:
            pass
        line = event.value.strip()
        if self._chat_busy:
            self._log_system("[yellow]Still working — Esc to cancel, then type again.[/]")
            return
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
                self._display_plan(generate=False)
                return
            if cmd == "/shield":
                self._log(self.bridge.cmd_shield())
                return
            if cmd == "/keys":
                from src.cli.api_key_providers import format_keys_report

                model_id = str(self.bridge.ctx.config.get("default_model", ""))
                self._log_user(line)
                self._log(
                    format_keys_report(
                        self.bridge.ctx.config, model_id, markup=True
                    )
                )
                self._refresh_chrome(sync_select=False)
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
                elif cmd in ("/plan", "/showplan", "/show-plan") or "MASTER PLAN" in result:
                    self._log(
                        "\n[bold #3fb950]══════════════════════════════════════[/]\n"
                        f"{result}\n"
                        "[bold #3fb950]══════════════════════════════════════[/]\n"
                    )
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

    def run_app(self) -> None:
        """Run TUI.

        Default: Textual mouse on — **click the chat or trace log**, then drag to select
        text (RichLog is now the scroll surface; an extra scroll wrapper broke selection).

        ``CE_NATIVE_COPY=1``: terminal owns mouse + **Ctrl+Shift+C**; use **PgUp** / **PgDn**
        to scroll. Chrome widgets use ``ChromeStatic`` so the rail does not join selection.
        """
        import os

        native = os.environ.get("CE_NATIVE_COPY", "0")
        use_mouse = native.strip().lower() not in ("1", "true", "yes")
        self.run(mouse=use_mouse)
