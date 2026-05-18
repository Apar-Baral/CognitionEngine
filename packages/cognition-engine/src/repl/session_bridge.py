"""Bridge REPL slash commands to ProjectContext and CLI logic."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.cli.context import ProjectContext, find_project_root
from src.cli.git_helpers import auto_commit, auto_commit_prefix, git_init_project, should_auto_commit
from src.core.config import Config


class SessionBridge:
    """Execute CE operations from the REPL without duplicating business rules."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or find_project_root()).resolve()
        self.ctx = ProjectContext(self.root)
        self._session_active = False

    def ensure_initialized(self) -> str | None:
        if not self.ctx.is_initialized():
            return "Project not initialized. Run /setup or cognition-engine init"
        return None

    def status_line(self) -> str:
        if not self.ctx.is_initialized():
            return "no project"
        phase = self.ctx.query.get_current_phase()
        model = self.ctx.config.get("default_model", "?")
        pid = phase.get("id", "—") if phase else "—"
        goal = self.ctx.get_project_goal()
        g = (goal[:40] + "…") if len(goal) > 40 else goal
        return f"{pid} | {model} | {g or 'no goal'}"

    def get_bootstrap_text(self) -> str:
        err = self.ensure_initialized()
        if err:
            return err
        boot = self.ctx.cognition_dir / "bootstrap.md"
        if boot.is_file():
            return boot.read_text(encoding="utf-8")
        return "No bootstrap.md — run /start"

    def cmd_help(self) -> str:
        return """Commands:
  /help              This help
  /model [ID]        Pick model (Ctrl+M) or set by ID
  /models            List registered models
  /goal TEXT         Set project goal
  /plan [goal]       Generate master plan
  /start [task]      Start session + refresh bootstrap
  /end SUMMARY       End session (+ auto-commit if enabled)
  /status            Project progress
  /budget            Token budget
  /commit MSG        Git commit now
  /setup             Run project setup wizard
  /chat TEXT         Send message to agent (requires API key)
  /exit              Quit"""

    def cmd_models(self) -> str:
        reg = self.ctx.model_registry()
        lines = ["ID | Tier"]
        for mid in reg.list_models()[:20]:
            m = reg.get_model(mid) or {}
            lines.append(f"{mid} | {m.get('tier', '?')}")
        return "\n".join(lines)

    def cmd_model(self, model_id: str) -> str:
        if not model_id.strip():
            return "Model picker: press [bold]Ctrl+M[/] or type /model <id>"
        mid = model_id.strip()
        reg = self.ctx.model_registry()
        if mid not in reg.list_models():
            known = ", ".join(reg.list_models()[:6])
            return f"Unknown model '{mid}'. Try /models or Ctrl+M. Known: {known}…"
        self.ctx.config.update("default_model", mid, persist=True)
        meta = reg.get_model(mid) or {}
        label = meta.get("display_name") or mid
        tier = meta.get("tier", "")
        from src.cli.setup_summary import load_last_setup, save_last_setup, save_project_setup_summary

        g = load_last_setup()
        g["default_model"] = mid
        save_last_setup(g)
        if self.ctx.is_initialized():
            ps = {"default_model": mid}
            save_project_setup_summary(self.root, ps)
        tier_note = f" [{tier}]" if tier else ""
        return f"Model updated to {mid} ({label}){tier_note} — saved to .cognition/config.yaml"

    def cmd_goal(self, text: str) -> str:
        if not text.strip():
            return self.ctx.get_project_goal() or "(no goal set)"
        self.ctx.set_project_goal(text)
        from src.cli.setup_wizard import _write_goal_file

        _write_goal_file(self.root, text)
        return "Goal updated."

    def cmd_plan(self, goal: str) -> str:
        err = self.ensure_initialized()
        if err:
            return err
        g = goal.strip() or self.ctx.get_project_goal()
        if not g:
            return "Provide goal: /plan Your project description"
        from src.planner.phase_generator import generate_goal_plan

        scan = self.ctx.scan()
        phases = generate_goal_plan(g, num_phases=24, language=scan["language"])
        self.ctx.save_plan(phases, goal=g)
        return f"Plan saved: {len(phases)} phases."

    def cmd_start(self, task: str = "") -> str:
        err = self.ensure_initialized()
        if err:
            return err
        phases = self.ctx.query.refresh().get("master_plan", {}).get("phase_sequence", [])
        if not phases:
            return "No plan. Run /plan first."
        from src.cli.commands import _apply_session_model

        _apply_session_model(self.ctx, None)
        gen = self.ctx.bootstrap_generator()
        bootstrap = gen.generate_and_save(task)
        budget = bootstrap.get("recommended_budget") or self.ctx.config.get_token_budget("BUILD")
        sid = int(bootstrap.get("session_id") or 1)
        self.ctx.save_session_state(
            {
                "session_id": sid,
                "budget": budget,
                "session_type": "BUILD",
                "model": self.ctx.config.get("default_model"),
            }
        )
        self._session_active = True
        return f"Session #{sid} started. Bootstrap: {self.ctx.cognition_dir / 'bootstrap.md'}"

    def cmd_end(self, summary: str) -> str:
        if not summary.strip():
            return "Usage: /end What you completed this session"
        state = self.ctx.load_session_state()
        if not state:
            return "No active session."
        op = self.ctx.active_operational_memory()
        op.set_completion_notes(summary)
        sess = op.get_session_summary()
        phase = self.ctx.query.get_current_phase()
        pid = phase.get("id", "PHASE_01") if phase else "PHASE_01"
        op.flush_to_dna(self.ctx.mutator, self.ctx.query, pid)
        self.ctx.session_store().close_session(int(state["session_id"]), sess)
        self.ctx.knowledge_synthesizer().synthesize(sess)
        self.ctx.clear_session_state()
        self._session_active = False
        lines = [f"Session ended: {summary[:80]}"]
        if should_auto_commit(self.ctx.config):
            msg = auto_commit(self.root, summary, prefix=auto_commit_prefix(self.ctx.config))
            if msg:
                lines.append(msg)
        return "\n".join(lines)

    def cmd_status(self) -> str:
        err = self.ensure_initialized()
        if err:
            return err
        dna = self.ctx.query.refresh()
        comp = self.ctx.query.calculate_project_completion()
        phase = self.ctx.query.get_current_phase()
        name = phase.get("name", "") if phase else ""
        return f"Progress: {comp:.0f}% | Phase: {phase.get('id') if phase else '—'} {name}"

    def cmd_budget(self) -> str:
        err = self.ensure_initialized()
        if err:
            return err
        state = self.ctx.load_session_state()
        budget = int(state.get("budget", 75000)) if state else self.ctx.config.get_token_budget("BUILD")
        return f"Session budget cap: {budget:,} tokens"

    def cmd_commit(self, message: str) -> str:
        from src.cli.git_helpers import auto_commit, is_git_repo

        if not is_git_repo(self.root):
            for m in git_init_project(self.root, initial_commit=False):
                pass
        msg = auto_commit(self.root, message or "session work", prefix="ce:")
        return msg or "Nothing committed."

    def cmd_setup(self) -> str:
        from src.cli.setup_wizard import run_full_setup

        run_full_setup(self.root, interactive=True)
        return "Setup complete — see sidebar for your choices."

    def dispatch(self, line: str) -> str:
        line = line.strip()
        if not line.startswith("/"):
            return ""
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/help": lambda: self.cmd_help(),
            "/h": lambda: self.cmd_help(),
            "/?": lambda: self.cmd_help(),
            "/models": lambda: self.cmd_models(),
            "/model": lambda: self.cmd_model(arg),
            "/goal": lambda: self.cmd_goal(arg),
            "/plan": lambda: self.cmd_plan(arg),
            "/start": lambda: self.cmd_start(arg),
            "/end": lambda: self.cmd_end(arg),
            "/status": lambda: self.cmd_status(),
            "/budget": lambda: self.cmd_budget(),
            "/commit": lambda: self.cmd_commit(arg),
            "/setup": lambda: self.cmd_setup(),
            "/chat": lambda: f"Use natural language (no /chat prefix). {arg}".strip(),
            "/bootstrap": lambda: self.get_bootstrap_text(),
            "/exit": lambda: "__EXIT__",
            "/quit": lambda: "__EXIT__",
        }
        fn = handlers.get(cmd)
        if fn is None:
            return f"Unknown command {cmd}. Try /help"
        return fn()
