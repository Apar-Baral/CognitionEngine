"""Bridge REPL slash commands to ProjectContext and CLI logic."""

from __future__ import annotations

import difflib
from pathlib import Path

from src.cli.context import ProjectContext, resolve_project_root
from src.cli.git_helpers import auto_commit, auto_commit_prefix, should_auto_commit


class SessionBridge:
    """Execute CE operations from the REPL without duplicating business rules."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or resolve_project_root()).resolve()
        self.ctx = ProjectContext(self.root)
        self._session_active = False

    def use_project(self, root: Path | str) -> None:
        """Rebind REPL to a project directory (after setup or /project)."""
        self.root = Path(root).expanduser().resolve()
        self.ctx = ProjectContext(self.root)
        self._session_active = False

    def ensure_initialized(self) -> str | None:
        if not self.ctx.is_initialized():
            return "Project not initialized. Run /setup or cognition-engine init"
        return None

    def status_line(self) -> str:
        if not self.ctx.is_initialized():
            return "no project"
        dna = self.ctx.query.refresh()
        phases = dna.get("master_plan", {}).get("phase_sequence", [])
        phase = self.ctx.query.get_current_phase()
        model = self.ctx.config.get("default_model", "?")
        pid = phase.get("id", "—") if phase else "—"
        goal = self.ctx.get_project_goal()
        g = (goal[:32] + "…") if len(goal) > 32 else goal
        if not phases:
            return f"{pid} | {model} | no plan"
        overall = self.ctx.query.calculate_project_completion()
        from src.core.constants import PhaseStatus

        done = sum(
            1 for p in phases if p.get("status") == PhaseStatus.COMPLETED.value
        )
        return (
            f"{pid} | {overall:.0f}% impl · {done}/{len(phases)} done | {model} | {g or 'no goal'}"
        )

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
  /plan [goal]       Generate + show master plan
  /showplan          Show saved plan in chat
  /shield            Hallucination shield — how it works
  /start [task]      Start session + refresh bootstrap
  /end SUMMARY       End session (+ auto-commit if enabled)
  /status            Project progress
  /budget            Token budget
  /commit MSG        Git commit now
  /setup             Run project setup wizard
  /project PATH      Switch to project directory
  /memory            DNA + sessions + insights summary
  /rl                Reinforcement learning (Q-table) status
  /keys              Which API keys are configured
  /copy              Copy full chat log (TUI command)
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
            return "Use the model dropdown in the top bar or Ctrl+M to search."
        from src.cli.model_picker import apply_model_choice

        return apply_model_choice(self.ctx, model_id.strip())

    def cmd_goal(self, text: str) -> str:
        if not text.strip():
            return self.ctx.get_project_goal() or "(no goal set)"
        self.ctx.set_project_goal(text)
        self._write_goal_file(text)
        self._refresh_bootstrap_preview_if_present()
        return "Goal updated."

    def _write_goal_file(self, text: str) -> None:
        from src.cli.setup_wizard import _write_goal_file

        _write_goal_file(self.root, text)

    def _refresh_bootstrap_preview_if_present(self) -> None:
        """Keep bootstrap.md aligned with the latest DNA goal without starting a session."""
        boot = self.ctx.cognition_dir / "bootstrap.md"
        if not boot.is_file():
            return
        try:
            gen = self.ctx.bootstrap_generator()
            ctx = gen.preview_bootstrap("")
            gen._save_bootstrap_file(ctx)  # keep existing Claude/CE context fresh
        except Exception:
            # Goal persistence must never fail just because bootstrap context is unavailable.
            return

    def cmd_plan(self, goal: str) -> str:
        err = self.ensure_initialized()
        if err:
            return err
        g = goal.strip() or self.ctx.get_project_goal()
        if not g:
            return "Provide goal: /plan Your project description"
        from src.planner.phase_generator import generate_goal_plan
        from src.repl.plan_display import format_plan_markup

        scan = self.ctx.scan()
        phases = generate_goal_plan(g, num_phases=24, language=scan["language"])
        self.ctx.save_plan(phases, goal=g)
        self._write_goal_file(g)
        self._refresh_bootstrap_preview_if_present()
        dna = self.ctx.query.refresh()
        overall = self.ctx.query.calculate_project_completion()
        name = dna.get("project", {}).get("name", self.root.name)
        return format_plan_markup(
            phases,
            goal=g,
            overall_completion=overall,
            project_name=str(name),
        )

    def cmd_show_plan(self) -> str:
        err = self.ensure_initialized()
        if err:
            return err
        from src.repl.plan_display import format_plan_markup, format_plan_plain

        dna = self.ctx.query.refresh()
        phases = dna.get("master_plan", {}).get("phase_sequence", [])
        if not phases:
            return "No plan yet. Set a goal (/goal …) then click Generate plan or /plan"
        goal = self.ctx.get_project_goal()
        overall = self.ctx.query.calculate_project_completion()
        name = dna.get("project", {}).get("name", self.root.name)
        plain = format_plan_plain(
            phases,
            goal=goal,
            overall_completion=overall,
            project_name=str(name),
        )
        rich = format_plan_markup(
            phases,
            goal=goal,
            overall_completion=overall,
            project_name=str(name),
        )
        return plain + "\n\n---\n\n" + rich

    def cmd_shield(self) -> str:
        from src.repl.plan_display import format_shield_detail

        return format_shield_detail(self.ctx)

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
            return "No active session. Run /start first."
        op = self.ctx.active_operational_memory()
        op.set_completion_notes(summary)
        sess = op.get_session_summary()
        phase = self.ctx.query.get_current_phase()
        pid = phase.get("id", "PHASE_01") if phase else "PHASE_01"
        op.flush_to_dna(self.ctx.mutator, self.ctx.query, pid)
        self.ctx.session_store().close_session(int(state["session_id"]), sess)
        new_insights = self.ctx.knowledge_synthesizer().synthesize(sess)
        rl = self.ctx.rl_allocator()
        alloc = rl.get_recommended_allocation(state.get("session_type", "BUILD"))
        rl.record_session_result(
            state.get("session_type", "BUILD"),
            "MEDIUM",
            alloc,
            float(sess.get("efficiency_score", 50)),
            outcome=sess,
        )
        try:
            from src.memory.vector_store import VectorMemoryStore

            VectorMemoryStore(self.root, self.ctx.project_name()).index_session_summary(sess)
        except Exception:
            pass
        self.ctx.clear_session_state()
        self._session_active = False
        lines = [
            f"Session ended: {summary[:80]}",
            f"Tokens: {sess.get('tokens', {}).get('total', 0)} | RL updated (Q-learning)",
        ]
        if new_insights:
            lines.append(f"New insights: {len(new_insights)}")
        if should_auto_commit(self.ctx.config):
            from src.cli.git_helpers import git_author_from_config

            author = git_author_from_config(self.ctx.config)
            msg = auto_commit(
                self.root,
                summary,
                prefix=auto_commit_prefix(self.ctx.config),
                author=author,
            )
            if msg:
                lines.append(msg)
            elif not author:
                lines.append(
                    "Git: auto_commit on but no git.user_name/email in ~/.cognition/config.yaml"
                )
        else:
            lines.append(
                "Git: auto_commit off — commit yourself: git add -A && git commit -m \"…\""
            )
        return "\n".join(lines)

    def cmd_memory(self) -> str:
        err = self.ensure_initialized()
        if err:
            return err
        dna = self.ctx.query.refresh()
        proj = dna.get("project", {})
        sessions = len(dna.get("sessions_index", []))
        insights = len(dna.get("insights", []))
        pending = len(self.ctx.query.get_unapplied_insights())
        hall = proj.get("total_hallucinations_caught", 0)
        tokens = proj.get("total_tokens_consumed", 0)
        return (
            f"Memory (DNA at {self.ctx.cognition_dir / 'dna.json'}):\n"
            f"  Sessions indexed: {sessions}\n"
            f"  Insights: {insights} ({pending} pending)\n"
            f"  Tokens tracked: {tokens}\n"
            f"  Hallucinations caught: {hall}\n"
            f"  Vector memory: optional (cognition-engine index)"
        )

    def cmd_rl(self) -> str:
        err = self.ensure_initialized()
        if err:
            return err
        rl = self.ctx.rl_allocator()
        stats = rl.get_learning_stats()
        dna = self.ctx.query.refresh().get("rl_state", {})
        return (
            "Reinforcement learning (token allocation Q-learning):\n"
            f"  States in Q-table: {stats.get('states_explored', 0)}\n"
            f"  Sessions learned: {stats.get('sessions_learned', 0)}\n"
            f"  Exploration ε: {stats.get('epsilon', dna.get('exploration_rate', '?'))}\n"
            f"  DNA sessions trained: {dna.get('total_sessions_trained', 0)}\n"
            f"  Updates on each /end — optimizes explore/implement/verify split"
        )

    def cmd_keys(self) -> str:
        from src.cli.api_key_providers import format_keys_report

        model_id = str(self.ctx.config.get("default_model", "?"))
        return format_keys_report(self.ctx.config, model_id, markup=False)

    def cmd_status(self) -> str:
        err = self.ensure_initialized()
        if err:
            return err
        from src.repl.plan_display import format_status_detail

        return format_status_detail(self.ctx)

    def cmd_budget(self) -> str:
        err = self.ensure_initialized()
        if err:
            return err
        state = self.ctx.load_session_state()
        budget = (
            int(state.get("budget", 75000))
            if state
            else self.ctx.config.get_token_budget("BUILD")
        )
        return f"Session budget cap: {budget:,} tokens"

    def cmd_commit(self, message: str) -> str:
        from src.cli.git_helpers import is_git_repo

        if not is_git_repo(self.root):
            return (
                "No git repo here. In your terminal:\n"
                "  git init && git add -A && git commit -m \"initial commit\""
            )
        text = (message or "describe your changes").strip().replace('"', "'")
        return (
            "CE does not run git commit for you — your name and email from git config are used.\n"
            f"In your terminal:\n"
            f'  cd "{self.root}"\n'
            f'  git add -A\n'
            f'  git commit -m "{text}"'
        )

    def cmd_project(self, path: str) -> str:
        if not path.strip():
            return f"Current project: {self.root} (initialized={self.ctx.is_initialized()})"
        target = Path(path.strip()).expanduser().resolve()
        if not target.is_dir():
            return f"Not a directory: {target}"
        self.use_project(target)
        if self.ctx.is_initialized():
            return f"Switched to project: {target}"
        return (
            f"Directory set to {target} but CE not initialized there.\n"
            "Run /setup or: cognition-engine setup --project ."
        )

    def cmd_setup(self) -> str:
        """Init .cognition only — model/keys use TUI Setup keys or `cognition-engine setup`."""
        if self.ctx.is_initialized():
            return (
                "Project already initialized.\n"
                "Set model & API keys: use [bold]Setup keys[/] in the UI, or run:\n"
                "  cognition-engine setup\n"
                "  export ANTHROPIC_API_KEY=...  (match your model provider)"
            )
        from src.cli.git_helpers import write_project_gitignore

        self.ctx.init_project()
        write_project_gitignore(self.root)
        self.use_project(self.root)
        return f"Initialized CE at {self.root}. Next: Setup keys (UI) or cognition-engine setup"

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
            "/showplan": lambda: self.cmd_show_plan(),
            "/shield": lambda: self.cmd_shield(),
            "/start": lambda: self.cmd_start(arg),
            "/end": lambda: self.cmd_end(arg),
            "/status": lambda: self.cmd_status(),
            "/budget": lambda: self.cmd_budget(),
            "/commit": lambda: self.cmd_commit(arg),
            "/copy": lambda: "Use Ctrl+Y or the Copy chat button in the TUI.",
            "/setup": lambda: self.cmd_setup(),
            "/project": lambda: self.cmd_project(arg),
            "/cd": lambda: self.cmd_project(arg),
            "/memory": lambda: self.cmd_memory(),
            "/rl": lambda: self.cmd_rl(),
            "/keys": lambda: self.cmd_keys(),
            "/chat": lambda: f"Use natural language (no /chat prefix). {arg}".strip(),
            "/bootstrap": lambda: self.get_bootstrap_text(),
            "/exit": lambda: "__EXIT__",
            "/quit": lambda: "__EXIT__",
        }
        fn = handlers.get(cmd)
        if fn is None:
            guess = difflib.get_close_matches(cmd, handlers.keys(), n=1)
            if guess:
                return f"Unknown command {cmd}. Did you mean {guess[0]}?"
            return f"Unknown command {cmd}. Try /help"
        return fn()


SLASH_COMMANDS: tuple[str, ...] = (
    "/?",
    "/bootstrap",
    "/budget",
    "/cd",
    "/chat",
    "/commit",
    "/copy",
    "/end",
    "/exit",
    "/goal",
    "/h",
    "/help",
    "/keys",
    "/memory",
    "/model",
    "/models",
    "/plan",
    "/project",
    "/quit",
    "/rl",
    "/setup",
    "/shield",
    "/show-plan",
    "/showplan",
    "/start",
    "/status",
)
