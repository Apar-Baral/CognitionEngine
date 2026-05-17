from __future__ import annotations

from pathlib import Path
from typing import Any

from cognition_engine.bootstrap.bootstrap_generator import BootstrapGenerator
from cognition_engine.core.constants import DEFAULT_SESSION_BUDGETS, SessionType
from cognition_engine.core.exceptions import NoActiveSessionError
from cognition_engine.core.paths import cognition_dir, find_project_root
from cognition_engine.dna.loader import DnaStore
from cognition_engine.dna.mutator import DnaMutator
from cognition_engine.dna.schema import empty_dna
from cognition_engine.memory.operational_memory import OperationalMemory
from cognition_engine.memory.session_store import SessionStore
from cognition_engine.planner.phase_generator import generate_meta_tool_plan, generate_simple_plan
from cognition_engine.scanner.project_scanner import scan_project
from cognition_engine.shield.import_validator import ImportValidator
from cognition_engine.shield.truth_index import TruthIndex, build_truth_index
from cognition_engine.token.budget_tracker import BudgetTracker
from cognition_engine.visualization.progress_map import render_progress_map


class CognitionService:
    def __init__(self, root: Path | None = None) -> None:
        self.root = find_project_root(root)
        self.store = DnaStore(self.root)

    def init_project(
        self,
        name: str | None = None,
        meta_tool: bool = False,
    ) -> dict[str, Any]:
        scan = scan_project(self.root)
        project_name = name or self.root.name
        dna = empty_dna(
            project_name=project_name,
            project_root=str(self.root),
            language=scan["language"],
        )
        mutator = DnaMutator(dna)
        phases = generate_meta_tool_plan() if meta_tool else generate_simple_plan(
            project_name, scan["language"]
        )
        mutator.set_phases(phases)
        if meta_tool or scan["language"] == "python":
            build_truth_index(self.root, scan["language"])
        self.store.save(dna)
        cognition_dir(self.root).mkdir(parents=True, exist_ok=True)
        return dna

    def start_session(
        self,
        session_type: str = "BUILD",
        budget: int | None = None,
    ) -> tuple[dict[str, Any], Any]:
        dna = self.store.load()
        op = OperationalMemory(self.root)
        if op.is_active():
            raise NoActiveSessionError("Session already active. Run `ce end` first.")

        st = SessionType(session_type) if session_type in SessionType.__members__ else SessionType.BUILD
        budget_tokens = budget or DEFAULT_SESSION_BUDGETS[st]

        mutator = DnaMutator(dna)
        session_id = mutator.start_session(st.value)
        mutator.set_session_budget(budget_tokens, st.value)

        phase = dna.get("current_phase_id")
        sub = dna.get("current_sub_task_id")
        SessionStore(self.root).log_start(session_id, phase, sub)
        op.start(session_id, st.value, budget_tokens)
        self.store.save(dna)

        packet = BootstrapGenerator(self.root, dna).generate()
        return dna, packet

    def end_session(
        self,
        summary: str,
        tokens: int = 0,
        files: list[str] | None = None,
        complete_sub_task: bool = False,
    ) -> dict[str, Any]:
        op = OperationalMemory(self.root)
        state = op.load()
        if not state or not state.get("active"):
            raise NoActiveSessionError("No active session. Run `ce start` first.")

        dna = self.store.load()
        mutator = DnaMutator(dna)
        session_id = state["session_id"]
        if tokens:
            mutator.add_tokens(tokens)
        mutator.end_session(
            session_id,
            summary=summary,
            files_modified=files,
            tokens_used=tokens or state.get("tokens_used", 0),
            sub_task_completed=complete_sub_task,
        )
        SessionStore(self.root).log_end(
            session_id, summary, tokens, files or []
        )
        op.clear()
        self.store.save(dna)
        return dna

    def status(self) -> str:
        dna = self.store.load()
        tracker = BudgetTracker(dna)
        lines = [render_progress_map(dna)]
        if OperationalMemory(self.root).is_active():
            lines.append("  [Active session]")
            lines.extend(f"  {l}" for l in tracker.status_lines())
        return "\n".join(lines)

    def budget_status(self) -> list[str]:
        dna = self.store.load()
        return BudgetTracker(dna).status_lines()

    def refresh_truth_index(self) -> TruthIndex:
        dna = self.store.load()
        lang = dna.get("project", {}).get("language", "python")
        return build_truth_index(self.root, lang)

    def validate_import(self, module: str) -> Any:
        index = TruthIndex.load(self.root)
        if not index:
            index = self.refresh_truth_index()
        return ImportValidator(index).validate_import_line(module)

    def validate_file(self, path: Path) -> list[Any]:
        index = TruthIndex.load(self.root)
        if not index:
            index = self.refresh_truth_index()
        return ImportValidator(index).validate_file(path)

    def record_hallucination(
        self,
        proposed: str,
        correct: str,
        category: str = "import_invention",
        context: str = "",
    ) -> None:
        dna = self.store.load()
        DnaMutator(dna).add_avoid_entry(category, proposed, correct, context)
        self.store.save(dna)
