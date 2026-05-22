"""
Stable public API for host integrations (Hermes plugin, MCP, etc.).

Avoid importing ``src.*`` from outside the package; use :class:`CognitionFacade`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.cli.context import ProjectContext, empty_dna, find_project_root, resolve_project_root
from src.core.constants import PhaseStatus
from src.planner.phase_generator import generate_goal_plan


class CognitionFacade:
    """Thin wrapper over :class:`ProjectContext` for external agents."""

    def __init__(self, root: Path | str | None = None) -> None:
        start = Path(root) if root else Path.cwd()
        self.root = resolve_project_root(start)
        self.ctx = ProjectContext(self.root)
        self._paths = None

    @property
    def cognition_dir(self) -> Path:
        return self.ctx.cognition_dir

    def is_initialized(self) -> bool:
        return self.ctx.is_initialized()

    def init_project(self, name: str | None = None, *, reinit: bool = False) -> dict[str, Any]:
        return self.ctx.init_project(name, reinit=reinit)

    def scan(self) -> dict[str, Any]:
        return self.ctx.scan()

    def set_goal(self, goal: str) -> None:
        self.ctx.require_initialized()
        self.ctx.set_project_goal(goal)

    def get_goal(self) -> str:
        return self.ctx.get_project_goal()

    def generate_plan(self, goal: str, *, num_phases: int = 24) -> list[dict[str, Any]]:
        self.ctx.require_initialized()
        scan = self.ctx.scan()
        phases = generate_goal_plan(goal, num_phases=num_phases, language=scan.get("language", "python"))
        self.ctx.save_plan(phases, goal=goal)
        return phases

    def start_session(
        self,
        task: str = "",
        *,
        budget: int | None = None,
        write_bootstrap_file: bool = True,
    ) -> dict[str, Any]:
        self.ctx.require_initialized()
        bootstrap = self.ctx.bootstrap_generator().generate_and_save(task, write_file=write_bootstrap_file)
        budget_tokens = budget or bootstrap.get("recommended_budget") or self.ctx.config.get_token_budget("BUILD")
        sid = int(bootstrap.get("session_id") or 1)
        self.ctx.save_session_state(
            {
                "session_id": sid,
                "budget": budget_tokens,
                "session_type": "BUILD",
            }
        )
        try:
            self.ctx.precompiler().warm_up()
        except Exception:
            pass
        return {
            "session_id": sid,
            "budget": budget_tokens,
            "bootstrap_text": bootstrap.get("context_text", ""),
            "bootstrap_path": str(self.ctx.cognition_dir / "bootstrap.md"),
            "phase_id": bootstrap.get("phase_id"),
        }

    def end_session(self, summary: str = "", *, tokens: int = 0) -> dict[str, Any]:
        self.ctx.require_initialized()
        state = self.ctx.load_session_state()
        if not state:
            return {"ended": False, "reason": "no_active_session"}

        op = self.ctx.active_operational_memory()
        if tokens:
            op.log_api_call("session", "aggregate", tokens // 2, tokens - tokens // 2)
        if summary:
            op.set_completion_notes(summary)
        sess_summary = op.get_session_summary()

        phase = self.ctx.query.get_current_phase()
        phase_id = phase.get("id", "PHASE_01") if phase else "PHASE_01"
        op.flush_to_dna(self.ctx.mutator, self.ctx.query, phase_id)
        self.ctx.session_store().close_session(int(state["session_id"]), sess_summary)

        predictor = self.ctx.bootstrap_generator().budget_predictor
        predictor.calibrate("BUILD", phase_id, sess_summary["tokens"]["total"], session_id=int(state["session_id"]))

        try:
            self.ctx.knowledge_synthesizer().synthesize(sess_summary)
        except Exception:
            pass
        try:
            self.ctx.rl_allocator().record_session_result(
                state.get("session_type", "BUILD"),
                "MEDIUM",
                self.ctx.rl_allocator().get_recommended_allocation(state.get("session_type", "BUILD")),
                float(sess_summary.get("efficiency_score", 50)),
                outcome=sess_summary,
            )
        except Exception:
            pass

        self.ctx.clear_session_state()
        return {"ended": True, "summary": sess_summary}

    def validate_code(
        self,
        file_path: str,
        proposed_content: str,
        *,
        original_content: str = "",
    ) -> dict[str, Any]:
        self.ctx.require_initialized()
        pipe = self.ctx.validation_pipeline(index_codebase=False)
        return pipe.validate_code_change(file_path, original_content, proposed_content)

    def status_text(self, *, detailed: bool = False, phase_id: str | None = None) -> str:
        from rich.console import Console

        from src.visualization.progress_bars import render_compact_progress, render_phase_detail, render_phase_progress_map

        self.ctx.require_initialized()
        dna = self.ctx.query.refresh()
        phases = dna.get("master_plan", {}).get("phase_sequence", [])
        console = Console(force_terminal=False, width=100)
        with console.capture() as cap:
            if phase_id:
                phase = self.ctx.query.get_phase_by_id(phase_id)
                if phase:
                    console.print(render_phase_detail(phase, project_name=self.ctx.project_name()))
            elif detailed:
                console.print(
                    render_phase_progress_map(
                        phases,
                        project_name=self.ctx.project_name(),
                        current_phase_index=dna["master_plan"].get("current_phase", 1),
                        overall_completion=self.ctx.query.calculate_project_completion(),
                    )
                )
            else:
                console.print(
                    render_compact_progress(
                        phases,
                        overall_completion=self.ctx.query.calculate_project_completion(),
                    )
                )
        return cap.get().strip()

    def budget_status(self) -> dict[str, Any]:
        state = self.ctx.load_session_state()
        if not state:
            return {"active": False}
        op = self.ctx.active_operational_memory()
        used = op.tokens_used
        limit = int(state.get("budget", 200000))
        ratio = used / limit if limit else 0.0
        from src.core.constants import budget_zone_for_ratio

        zone = budget_zone_for_ratio(ratio)
        return {"active": True, "used": used, "limit": limit, "ratio": ratio, "zone": zone.value}

    def record_api_tokens(self, tokens: int) -> None:
        state = self.ctx.load_session_state()
        if state:
            self.ctx.active_operational_memory().log_api_call("hermes", "chat", tokens // 2, tokens - tokens // 2)

    def get_bootstrap_for_injection(self) -> str:
        path = self.ctx.cognition_dir / "bootstrap.md"
        if path.is_file():
            return path.read_text(encoding="utf-8")
        if self.ctx.is_initialized():
            try:
                ctx = self.ctx.bootstrap_generator().preview_bootstrap()
                return ctx.get("context_text", "")
            except Exception:
                pass
        return ""

    def migrate_legacy_data_dir(self) -> Path:
        """Copy .hermes/cognition/ → .cognition/ when only legacy exists."""
        legacy = self.root / ".hermes" / "cognition"
        target = self.root / ".cognition"
        if target.joinpath("dna.json").is_file():
            return target
        if not legacy.joinpath("dna.json").is_file():
            return target
        import shutil

        target.mkdir(parents=True, exist_ok=True)
        for item in legacy.iterdir():
            dest = target / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copytree(item, dest)
            else:
                shutil.copy2(item, dest)
        dna = self.ctx.loader.load() if self.ctx.is_initialized() else empty_dna(self.root.name)
        meta = dna.setdefault("project", {})
        meta["migrated_from"] = str(legacy)
        if self.ctx.is_initialized():
            self.ctx.loader.save(dna)
        return target


def open_project(root: Path | str | None = None) -> CognitionFacade:
    return CognitionFacade(root)
