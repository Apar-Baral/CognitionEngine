"""
Safe DNA mutation layer — all writes go through here.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.core.constants import PhaseStatus, TaskStatus, VALID_PHASE_TRANSITIONS
from src.core.exceptions import DNAValidationError, InvalidTransitionError
from src.dna.loader import DNALoader

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DNAMutator:
    """Atomic mutations with validation and audit logging."""

    def __init__(self, loader: DNALoader) -> None:
        self.loader = loader

    def _mutate(self, fn_name: str, apply: Any) -> dict[str, Any]:
        dna = self.loader.load(force_reload=True)
        snapshot = _deep_copy(dna)
        try:
            apply(dna)
            self.loader.save(dna)
            logger.info("DNA mutation %s succeeded", fn_name)
            return dna
        except Exception:
            logger.exception("DNA mutation %s failed; rolling back", fn_name)
            try:
                self.loader.save(snapshot)
            except Exception:
                logger.exception("Rollback save failed")
            raise

    def update_phase_status(
        self,
        phase_id: str,
        new_status: str | PhaseStatus,
        session_id: int,
        reason: str = "",
    ) -> dict[str, Any]:
        new_val = new_status.value if isinstance(new_status, PhaseStatus) else new_status

        def apply(dna: dict[str, Any]) -> None:
            phase = _find_phase(dna, phase_id)
            if not phase:
                raise DNAValidationError(f"Unknown phase {phase_id}")
            current = PhaseStatus(phase["status"])
            target = PhaseStatus(new_val)
            allowed = VALID_PHASE_TRANSITIONS.get(current, frozenset())
            if target not in allowed:
                raise InvalidTransitionError(
                    f"Cannot transition {phase_id} from {current.value} to {new_val}",
                    current_state=current.value,
                    attempted_state=new_val,
                    valid_options=[s.value for s in allowed],
                )
            phase["state_history"].append(
                {
                    "from_state": current.value,
                    "to_state": new_val,
                    "timestamp": _utc_now(),
                    "session_id": session_id,
                    "reason": reason or "update_phase_status via DNAMutator",
                }
            )
            phase["status"] = new_val
            if target == PhaseStatus.IN_PROGRESS and not phase.get("started"):
                phase["started"] = datetime.now(timezone.utc).date().isoformat()
            if target == PhaseStatus.COMPLETED:
                phase["completed"] = datetime.now(timezone.utc).date().isoformat()
                phase["completion_score"] = 100

        return self._mutate("update_phase_status", apply)

    def update_subtask_progress(
        self,
        phase_id: str,
        subtask_id: str,
        progress: int,
        status: str | TaskStatus | None = None,
    ) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            phase = _find_phase(dna, phase_id)
            if not phase:
                raise DNAValidationError(f"Unknown phase {phase_id}")
            st = _find_subtask(phase, subtask_id)
            if not st:
                raise DNAValidationError(f"Unknown sub-task {subtask_id} in {phase_id}")
            st["progress"] = max(0, min(100, progress))
            if status is not None:
                st["status"] = status.value if isinstance(status, TaskStatus) else status
                st["last_worked_on"] = _utc_now()
            if progress >= 100 and st.get("status") != TaskStatus.DONE.value:
                st["status"] = TaskStatus.DONE.value

            subs = phase.get("sub_tasks", [])
            if subs and all(
                s.get("status") == TaskStatus.DONE.value for s in subs if isinstance(s, dict)
            ):
                if phase.get("status") == PhaseStatus.IN_PROGRESS.value:
                    logger.info(
                        "Phase %s: all sub-tasks DONE; consider IN_REVIEW", phase_id
                    )

        return self._mutate("update_subtask_progress", apply)

    def add_session_record(
        self,
        session_id: int,
        started_at: str,
        ended_at: str,
        phase_id: str,
        session_type: str,
        tokens_consumed: int,
        efficiency_score: float,
        completion_notes: str = "",
    ) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            entry: dict[str, Any] = {
                "session_id": session_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "phase_id": phase_id,
                "session_type": session_type,
                "tokens_consumed": tokens_consumed,
                "efficiency_score": efficiency_score,
            }
            if completion_notes:
                entry["completion_notes"] = completion_notes
            dna.setdefault("sessions_index", []).append(entry)
            proj = dna.setdefault("project", {})
            proj["total_sessions"] = len(dna["sessions_index"])
            proj["total_tokens_consumed"] = proj.get("total_tokens_consumed", 0) + tokens_consumed
            proj["last_updated"] = _utc_now()

        return self._mutate("add_session_record", lambda d: apply(d))

    def add_hallucination(
        self,
        record: dict[str, Any],
        session_id: int | None = None,
    ) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            reg = dna.setdefault("avoid_registry", {})
            reg.setdefault("hallucinations", []).append(record)
            dna["project"]["total_hallucinations_caught"] = (
                dna["project"].get("total_hallucinations_caught", 0) + 1
            )

        return self._mutate(
            "add_hallucination",
            apply,
        )

    def add_failed_approach(self, record: dict[str, Any]) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            reg = dna.setdefault("avoid_registry", {})
            reg.setdefault("failed_approaches", []).append(record)

        return self._mutate("add_failed_approach", apply)

    def add_understood_file(self, path: str) -> dict[str, Any]:
        norm = path.replace("\\", "/")

        def apply(dna: dict[str, Any]) -> None:
            reg = dna.setdefault("avoid_registry", {})
            files = set(reg.get("understood_files", []))
            files.add(norm)
            reg["understood_files"] = sorted(files)

        return self._mutate("add_understood_file", apply)

    def add_deprecated_pattern(self, pattern: str) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            reg = dna.setdefault("avoid_registry", {})
            patterns = reg.setdefault("deprecated_patterns", [])
            if pattern not in patterns:
                patterns.append(pattern)

        return self._mutate("add_deprecated_pattern", apply)

    def manage_avoid_decay(self, accessed_ids: set[str]) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            reg = dna.setdefault("avoid_registry", {})
            for key in ("hallucinations", "failed_approaches"):
                for item in reg.get(key, []):
                    if not isinstance(item, dict):
                        continue
                    iid = item.get("id", "")
                    if iid in accessed_ids:
                        item["decay_count"] = 0
                    else:
                        item["decay_count"] = item.get("decay_count", 0) + 1

        return self._mutate("manage_avoid_decay", apply)

    def add_insight(self, insight: dict[str, Any]) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            if "id" not in insight:
                insight["id"] = f"INS_{uuid.uuid4().hex[:8].upper()}"
            dna.setdefault("insights", []).append(insight)

        return self._mutate("add_insight", apply)

    def update_architecture_node(
        self,
        node_id: str,
        *,
        status: str | None = None,
        files: list[str] | None = None,
        dependencies: list[str] | None = None,
        session_id: int | None = None,
    ) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            node = _find_node(dna, node_id)
            if not node:
                raise DNAValidationError(f"Unknown architecture node {node_id}")
            if status is not None:
                node["status"] = status
            if files is not None:
                node["files"] = files
            if dependencies is not None:
                node["dependencies"] = dependencies
            if session_id is not None:
                node["last_modified_in_session"] = session_id

        return self._mutate("update_architecture_node", apply)

    def add_emergent_feature(self, feature: dict[str, Any]) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            if "id" not in feature:
                feature["id"] = f"FEAT_{uuid.uuid4().hex[:6].upper()}"
            dna.setdefault("feature_registry", {}).setdefault(
                "emergent_features", []
            ).append(feature)

        return self._mutate("add_emergent_feature", apply)

    def add_deviation(self, deviation: dict[str, Any]) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            dna.setdefault("deviation_history", []).append(deviation)

        return self._mutate("add_deviation", apply)

    def update_recommendation(
        self,
        recommendation_id: str,
        accepted: bool,
    ) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            for rec in dna.get("recommendations", []):
                if rec.get("id") == recommendation_id:
                    rec["accepted"] = accepted
                    return
            raise DNAValidationError(f"Unknown recommendation {recommendation_id}")

        return self._mutate("update_recommendation", apply)

    def update_rl_state(
        self,
        q_table: dict[str, Any] | None = None,
        learning_rate: float | None = None,
        exploration_rate: float | None = None,
        increment_sessions: bool = False,
    ) -> dict[str, Any]:
        def apply(dna: dict[str, Any]) -> None:
            rl = dna.setdefault(
                "rl_state",
                {
                    "q_table": {},
                    "learning_rate": 0.1,
                    "exploration_rate": 0.1,
                    "total_sessions_trained": 0,
                },
            )
            if q_table is not None:
                rl["q_table"] = q_table
            if learning_rate is not None:
                rl["learning_rate"] = learning_rate
            if exploration_rate is not None:
                rl["exploration_rate"] = exploration_rate
            if increment_sessions:
                rl["total_sessions_trained"] = rl.get("total_sessions_trained", 0) + 1

        return self._mutate("update_rl_state", apply)


def _find_phase(dna: dict[str, Any], phase_id: str) -> dict[str, Any] | None:
    for p in dna.get("master_plan", {}).get("phase_sequence", []):
        if isinstance(p, dict) and p.get("id") == phase_id:
            return p
    return None


def _find_subtask(phase: dict[str, Any], subtask_id: str) -> dict[str, Any] | None:
    for st in phase.get("sub_tasks", []):
        if isinstance(st, dict) and st.get("id") == subtask_id:
            return st
    return None


def _find_node(dna: dict[str, Any], node_id: str) -> dict[str, Any] | None:
    for n in dna.get("architecture_graph", {}).get("nodes", []):
        if isinstance(n, dict) and n.get("id") == node_id:
            return n
    return None


def _deep_copy(dna: dict[str, Any]) -> dict[str, Any]:
    import copy

    return copy.deepcopy(dna)


__all__ = ["DNAMutator"]
