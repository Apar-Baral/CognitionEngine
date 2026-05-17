"""
Per-phase tactical memory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.core.constants import TaskStatus
from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery


class TacticalMemory:
    """Detailed memory for one active phase."""

    def __init__(
        self,
        query: DNAQuery,
        phase_id: str,
        mutator: DNAMutator | None = None,
    ) -> None:
        self.query = query
        self.phase_id = phase_id
        self.mutator = mutator
        self._file_access_log: list[dict[str, Any]] = []
        self._decisions: list[dict[str, Any]] = []
        self._gotchas: list[str] = []
        self._active_subtask_id: str | None = None

    def get_active_context(self) -> dict[str, Any]:
        phase = self.query.get_phase_by_id(self.phase_id)
        if not phase:
            return {"phase_id": self.phase_id, "found": False}

        active_st = self._active_subtask_id
        if not active_st:
            for st in phase.get("sub_tasks", []):
                if isinstance(st, dict) and st.get("status") == TaskStatus.IN_PROGRESS.value:
                    active_st = st.get("id")
                    break

        understood = self.query._data().get("avoid_registry", {}).get("understood_files", [])
        files_modified: list[str] = []
        for st in phase.get("sub_tasks", []):
            if isinstance(st, dict):
                files_modified.extend(st.get("files_modified", []))

        remaining_tokens = max(
            0, phase.get("estimated_tokens", 0) - phase.get("tokens_consumed", 0)
        )
        pending = sum(
            1
            for st in phase.get("sub_tasks", [])
            if isinstance(st, dict) and st.get("status") != TaskStatus.DONE.value
        )

        return {
            "found": True,
            "phase_id": self.phase_id,
            "name": phase.get("name"),
            "description": phase.get("description"),
            "sub_tasks": phase.get("sub_tasks", []),
            "active_sub_task_id": active_st,
            "files_modified_in_phase": list(dict.fromkeys(files_modified)),
            "understood_files": understood,
            "recent_decisions": phase.get("state_history", [])[-5:] + self._decisions[-5:],
            "gotchas": list(self._gotchas),
            "estimated_remaining_tokens": remaining_tokens,
            "estimated_remaining_sessions": max(1, pending),
        }

    def get_relevant_files(self, sub_task_id: str | None = None) -> list[dict[str, Any]]:
        phase = self.query.get_phase_by_id(self.phase_id)
        if not phase:
            return []

        scored: dict[str, float] = {}
        st_id = sub_task_id or self._active_subtask_id
        if st_id:
            st = next(
                (s for s in phase.get("sub_tasks", []) if s.get("id") == st_id),
                None,
            )
            if st:
                for f in st.get("files_modified", []):
                    scored[f] = scored.get(f, 0) + 10.0

        for node in self.query._data().get("architecture_graph", {}).get("nodes", []):
            if not isinstance(node, dict):
                continue
            if node.get("created_in_phase") == self.phase_id:
                for f in node.get("files", []):
                    scored[f] = scored.get(f, 0) + 5.0

        for entry in self._file_access_log[-20:]:
            path = entry.get("path", "")
            scored[path] = scored.get(path, 0) + 3.0

        for path in self.query._data().get("avoid_registry", {}).get("understood_files", []):
            scored[path] = scored.get(path, 0) - 2.0

        return [
            {"path": p, "relevance": s}
            for p, s in sorted(scored.items(), key=lambda x: -x[1])
            if s > 0
        ]

    def record_file_access(
        self,
        path: str,
        operation: str,
        content_hash: str,
    ) -> None:
        self._file_access_log.append(
            {
                "path": path,
                "operation": operation,
                "content_hash": content_hash,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def record_decision(
        self,
        decision: str,
        rationale: str,
        alternatives: list[str] | None = None,
        sub_task_id: str | None = None,
    ) -> None:
        self._decisions.append(
            {
                "decision": decision,
                "rationale": rationale,
                "alternatives": alternatives or [],
                "sub_task_id": sub_task_id or self._active_subtask_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def is_file_understood(self, path: str) -> bool:
        understood = self.query._data().get("avoid_registry", {}).get("understood_files", [])
        norm = path.replace("\\", "/")
        return norm in understood or path in understood

    def get_phase_efficiency(self) -> dict[str, Any]:
        phase = self.query.get_phase_by_id(self.phase_id)
        if not phase:
            return {}
        estimated = max(phase.get("estimated_tokens", 1), 1)
        consumed = phase.get("tokens_consumed", 0)
        subs = phase.get("sub_tasks", [])
        done = sum(1 for s in subs if s.get("status") == TaskStatus.DONE.value)
        sessions = max(phase.get("sessions_used", 1), 1)
        phase_sessions = self.query.get_sessions_for_phase(self.phase_id)
        hallucinations = self.query._data().get("project", {}).get(
            "total_hallucinations_caught", 0
        )
        return {
            "token_ratio": round(consumed / estimated, 3),
            "sessions_used": phase.get("sessions_used", 0),
            "subtasks_per_session": round(done / sessions, 2),
            "subtasks_completed": done,
            "subtasks_total": len(subs),
            "hallucinations_project_total": hallucinations,
            "sessions_in_index": len(phase_sessions),
        }

    def mark_subtask_active(self, sub_task_id: str) -> None:
        self._active_subtask_id = sub_task_id
        if self.mutator:
            phase = self.query.get_phase_by_id(self.phase_id)
            if phase:
                for st in phase.get("sub_tasks", []):
                    if isinstance(st, dict) and st.get("id") == sub_task_id:
                        if st.get("status") == TaskStatus.PENDING.value:
                            self.mutator.update_subtask_progress(
                                self.phase_id,
                                sub_task_id,
                                st.get("progress", 0),
                                TaskStatus.IN_PROGRESS,
                            )
                        break

    def flush(self) -> None:
        """Persist tactical notes to DNA (understood files, insights)."""
        if not self.mutator:
            return
        dna = self.query.refresh()
        reg = dna.setdefault("avoid_registry", {})
        understood = set(reg.get("understood_files", []))
        for entry in self._file_access_log:
            if entry.get("operation") == "read" and entry.get("marked_understood"):
                understood.add(entry["path"])
        reg["understood_files"] = sorted(understood)
        for decision in self._decisions:
            self.mutator.add_insight(
                {
                    "type": "decision",
                    "finding": decision["decision"],
                    "confidence": 0.9,
                    "generated_at": decision["timestamp"],
                    "session_id": 0,
                    "actionability": "MEDIUM",
                    "applied": False,
                }
            )
        self.query.refresh()
