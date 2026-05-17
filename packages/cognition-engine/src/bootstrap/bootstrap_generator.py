"""
Orchestrate session bootstrap from memory, avoid register, and budget prediction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.bootstrap.avoid_register import AvoidRegister
from src.bootstrap.budget_predictor import BudgetPredictor, TaskComplexity
from src.bootstrap.context_compiler import ContextCompiler, estimate_tokens
from src.core.constants import BOOTSTRAP_MAX_TOKENS, SessionType, TaskStatus
from src.core.types import BootstrapContext
from src.dna.query import DNAQuery
from src.memory.session_store import SessionStore
from src.memory.strategic_memory import StrategicMemory
from src.memory.tactical_memory import TacticalMemory


def infer_session_type(sub_task: dict[str, Any] | None, phase: dict[str, Any]) -> SessionType:
    """Map sub-task / phase metadata to a session type."""
    name = (sub_task.get("name") if sub_task else "") or ""
    lower = name.lower()
    if any(k in lower for k in ("debug", "fix", "bug", "regression")):
        return SessionType.DEBUG
    if "refactor" in lower:
        return SessionType.REFACTOR
    if any(k in lower for k in ("explore", "spike", "research")):
        return SessionType.EXPLORE
    if any(k in lower for k in ("integrat", "wire", "connect")):
        return SessionType.INTEGRATE
    if "optim" in lower:
        return SessionType.OPTIMIZE
    phase_type = phase.get("phase_type", SessionType.BUILD.value)
    try:
        return SessionType(phase_type)
    except ValueError:
        return SessionType.BUILD


def infer_complexity(sub_task: dict[str, Any] | None) -> TaskComplexity:
    if not sub_task:
        return "MEDIUM"
    est = sub_task.get("estimated_tokens", 5000)
    if est < 3000:
        return "LOW"
    if est > 12000:
        return "HIGH"
    return "MEDIUM"


class BootstrapGenerator:
    """Produce BootstrapContext for a new coding session."""

    def __init__(
        self,
        strategic: StrategicMemory,
        tactical: TacticalMemory,
        compiler: ContextCompiler,
        avoid_register: AvoidRegister,
        budget_predictor: BudgetPredictor,
        query: DNAQuery,
        session_store: SessionStore | None = None,
        project_root: Path | str | None = None,
    ) -> None:
        self.strategic = strategic
        self.tactical = tactical
        self.compiler = compiler
        self.avoid_register = avoid_register
        self.budget_predictor = budget_predictor
        self.query = query
        self.session_store = session_store
        self.project_root = Path(project_root) if project_root else Path.cwd()

    def generate(self, task_description: str = "") -> BootstrapContext:
        """Run the full bootstrap pipeline and return BootstrapContext."""
        state = self.strategic.get_current_state()
        phase_id = state.get("phase_id") or ""
        phase = self.query.get_phase_by_id(phase_id) if phase_id else None

        if phase_id and phase:
            tactical = TacticalMemory(self.query, phase_id)
            tactical_ctx = tactical.get_active_context()
        else:
            tactical = self.tactical
            tactical_ctx = tactical.get_active_context()

        active_sub = _active_subtask(state, tactical_ctx)
        sub_id = active_sub.get("id") if active_sub else ""
        context_text = task_description or (
            (active_sub.get("next_action") if active_sub else None)
            or (active_sub.get("name") if active_sub else "")
            or "Continue project work"
        )

        avoid_items = self.avoid_register.get_relevant_avoid_items(context_text, limit=5)
        for item in avoid_items:
            if item.get("_category") == "hallucination":
                item["priority"] = "critical"

        session_type = infer_session_type(active_sub, phase or {})
        files_count = len(active_sub.get("files_modified", [])) if active_sub else 3
        complexity = infer_complexity(active_sub)

        prediction = self.budget_predictor.predict(
            session_type,
            phase_id or "UNKNOWN",
            files_count,
            complexity,
        )
        recommended = self.budget_predictor.get_recommended_budget(prediction)

        last_session = self.query.get_most_recent_session()
        last_files: list[str] = []
        last_decisions: list[dict[str, Any]] = []
        if last_session:
            last_files = list(last_session.get("files_modified", []))
        if phase:
            last_decisions = list(phase.get("state_history", []))[-3:]

        arch_nodes: list[dict[str, Any]] = []
        if active_sub:
            for path in active_sub.get("files_modified", [])[:5]:
                arch_nodes.extend(self.query.find_components_affected_by_file(path))

        phase_sessions = self.query.get_sessions_for_phase(phase_id) if phase_id else []
        session_summary = (
            f"{len(phase_sessions)} session(s) on this phase"
            if phase_sessions
            else None
        )

        self.compiler.tactical = tactical
        relevant = tactical.get_relevant_files(sub_id) if phase_id else []
        file_paths = [r["path"] for r in relevant[:10]]

        compiled = self.compiler.compile_context(
            context_text,
            BOOTSTRAP_MAX_TOKENS,
            avoid_items=avoid_items,
            last_session_files=last_files,
            last_session_decisions=last_decisions,
            relevant_file_paths=file_paths,
            architecture_nodes=arch_nodes,
            session_history_summary=session_summary,
            project_root=self.project_root,
        )

        session_id = ""
        if self.session_store:
            sid = self.session_store.create_session(
                phase_id=phase_id,
                session_type=session_type.value,
            )
            session_id = str(sid)
            self.session_store.write_event(
                sid,
                "bootstrap_generated",
                {
                    "phase_id": phase_id,
                    "sub_task_id": sub_id,
                    "predicted_tokens": prediction["estimated_tokens"],
                    "recommended_budget": recommended,
                    "avoid_count": len(avoid_items),
                    "context_tokens": estimate_tokens(compiled),
                },
            )

        ts = datetime.now(timezone.utc).isoformat()
        return BootstrapContext(
            session_id=session_id,
            generated_timestamp=ts,
            context_text=compiled,
            token_count=estimate_tokens(compiled),
            phase_id=phase_id,
            sub_task_id=sub_id,
            predicted_tokens=prediction["estimated_tokens"],
            recommended_budget=recommended,
            avoid_items_included=[
                item.get("description", item.get("id", ""))[:120] for item in avoid_items
            ],
        )


def _active_subtask(
    state: dict[str, Any],
    tactical_ctx: dict[str, Any],
) -> dict[str, Any] | None:
    active_id = tactical_ctx.get("active_sub_task_id")
    subs = state.get("all_sub_tasks") or tactical_ctx.get("sub_tasks", [])
    for st in subs:
        if not isinstance(st, dict):
            continue
        if active_id and st.get("id") == active_id:
            return st
        if st.get("status") == TaskStatus.IN_PROGRESS.value:
            return st
    active_list = state.get("active_sub_tasks", [])
    return active_list[0] if active_list else None
