"""
Orchestrate session bootstrap from memory, avoid register, and budget prediction.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.bootstrap.avoid_register import AvoidRegister
from src.bootstrap.bootstrap_formatter import BootstrapParts, format_bootstrap
from src.bootstrap.budget_predictor import BudgetPredictor, TaskComplexity
from src.bootstrap.context_compiler import ContextCompiler, estimate_tokens
from src.core.constants import BOOTSTRAP_MAX_TOKENS, COGNITION_DIR, SessionType, TaskStatus
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
        *,
        default_model_id: str = "claude-sonnet",
    ) -> None:
        self.strategic = strategic
        self.tactical = tactical
        self.compiler = compiler
        self.avoid_register = avoid_register
        self.budget_predictor = budget_predictor
        self.query = query
        self.session_store = session_store
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.default_model_id = default_model_id

    def preview_bootstrap(self, task_description: str = "") -> BootstrapContext:
        """Generate bootstrap without creating a session or writing files."""
        parts, meta = self._prepare(task_description)
        parts.session_id = "PREVIEW"
        return self._assemble(parts, meta, persist_session=False)

    def generate(self, task_description: str = "") -> BootstrapContext:
        """Run the full bootstrap pipeline and return BootstrapContext."""
        return self.generate_and_save(task_description, write_file=False)

    def generate_and_save(
        self,
        task_description: str = "",
        *,
        write_file: bool = True,
    ) -> BootstrapContext:
        """Generate bootstrap, log to session store, optionally write bootstrap.md."""
        parts, meta = self._prepare(task_description)
        ctx = self._assemble(parts, meta, persist_session=True)
        if write_file:
            self._save_bootstrap_file(ctx)
        return ctx

    def _prepare(
        self,
        task_description: str,
    ) -> tuple[BootstrapParts, dict[str, Any]]:
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
        objective = task_description or (
            (active_sub.get("next_action") if active_sub else None)
            or (active_sub.get("name") if active_sub else "")
            or "Continue project work"
        )

        avoid_items_raw = self.avoid_register.get_relevant_avoid_items(objective, limit=5)
        for item in avoid_items_raw:
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
        cost = self.budget_predictor.get_cost_estimate(prediction, self.default_model_id)

        last_session = self.query.get_most_recent_session()
        prev_sid = str(last_session.get("session_id", "")) if last_session else ""
        last_files: list[str] = []
        last_decisions: list[dict[str, Any]] = []
        if last_session:
            last_files = list(last_session.get("files_modified", []))
        if phase:
            last_decisions = list(phase.get("state_history", []))[-3:]

        self.compiler.tactical = tactical
        relevant = tactical.get_relevant_files(sub_id) if phase_id else []
        file_summaries: list[tuple[str, str]] = []
        for r in relevant[:10]:
            path = r["path"]
            summary = self.compiler.summarize_file(
                self.project_root / path if not Path(path).is_absolute() else path
            )
            if " — " in summary:
                _, desc = summary.split(" — ", 1)
            else:
                desc = summary
            file_summaries.append((path, desc))

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

        supplementary = self.compiler.compile_context(
            objective,
            BOOTSTRAP_MAX_TOKENS,
            avoid_items=avoid_items_raw,
            last_session_files=last_files,
            last_session_decisions=last_decisions,
            relevant_file_paths=[p for p, _ in file_summaries],
            architecture_nodes=arch_nodes,
            session_history_summary=session_summary,
            project_root=self.project_root,
        )

        parts = BootstrapParts(
            phase_id=phase_id or "—",
            phase_name=state.get("name", "—") if state.get("active") else "—",
            phase_completion=float(state.get("completion_percentage", 0)),
            subtask_id=sub_id or "—",
            subtask_name=(active_sub.get("name") if active_sub else "—") or "—",
            subtask_progress=int(active_sub.get("progress", 0)) if active_sub else 0,
            objective=objective,
            previous_session_id=prev_sid,
            last_completed=(
                last_session.get("completion_notes", "")
                if last_session
                else (phase_sessions[-1].get("session_type", "") if phase_sessions else "")
            ),
            last_decisions=[
                self.compiler.summarize_decision(d)
                for d in reversed(last_decisions[-3:])
                if isinstance(d, dict)
            ],
            last_files_modified=last_files or list(state.get("files_being_modified", [])),
            last_unfinished=active_sub.get("next_action", "") if active_sub else "",
            relevant_files=file_summaries,
            avoid_items=[
                str(item.get("description", item.get("id", "")))[:200]
                for item in avoid_items_raw
            ],
            predicted_tokens=int(prediction["estimated_tokens"]),
            recommended_budget=recommended,
            cost_estimate=cost,
            supplementary=supplementary,
        )

        meta = {
            "phase_id": phase_id,
            "sub_task_id": sub_id,
            "session_type": session_type,
            "prediction": prediction,
            "avoid_items_raw": avoid_items_raw,
            "recommended": recommended,
        }
        return parts, meta

    def _assemble(
        self,
        parts: BootstrapParts,
        meta: dict[str, Any],
        *,
        persist_session: bool,
    ) -> BootstrapContext:
        if persist_session and self.session_store:
            sid = self.session_store.create_session(
                phase_id=meta["phase_id"],
                session_type=meta["session_type"].value,
            )
            parts.session_id = str(sid)
        else:
            parts.session_id = parts.session_id or "PREVIEW"

        context_text = format_bootstrap(parts, BOOTSTRAP_MAX_TOKENS)
        ts = datetime.now(timezone.utc).isoformat()

        if persist_session and self.session_store and parts.session_id != "PREVIEW":
            self.session_store.write_event(
                int(parts.session_id),
                "bootstrap_generated",
                {
                    "phase_id": meta["phase_id"],
                    "sub_task_id": meta["sub_task_id"],
                    "predicted_tokens": parts.predicted_tokens,
                    "recommended_budget": parts.recommended_budget,
                    "avoid_count": len(meta["avoid_items_raw"]),
                    "context_tokens": estimate_tokens(context_text),
                },
            )

        return BootstrapContext(
            session_id=parts.session_id,
            generated_timestamp=ts,
            context_text=context_text,
            token_count=estimate_tokens(context_text),
            phase_id=meta["phase_id"],
            sub_task_id=meta["sub_task_id"],
            predicted_tokens=parts.predicted_tokens,
            recommended_budget=parts.recommended_budget,
            avoid_items_included=parts.avoid_items,
        )

    def _save_bootstrap_file(self, ctx: BootstrapContext) -> Path:
        cog = self.project_root / COGNITION_DIR
        cog.mkdir(parents=True, exist_ok=True)
        path = cog / "bootstrap.md"
        path.write_text(ctx.get("context_text", ""), encoding="utf-8")
        meta_path = cog / "bootstrap_meta.json"
        import json

        meta_path.write_text(
            json.dumps(
                {
                    "session_id": ctx.get("session_id"),
                    "generated_timestamp": ctx.get("generated_timestamp"),
                    "token_count": ctx.get("token_count"),
                    "phase_id": ctx.get("phase_id"),
                    "sub_task_id": ctx.get("sub_task_id"),
                    "predicted_tokens": ctx.get("predicted_tokens"),
                    "recommended_budget": ctx.get("recommended_budget"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return path


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
