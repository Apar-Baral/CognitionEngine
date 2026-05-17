"""
Read-only DNA query interface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.core.constants import ComponentStatus, PhaseStatus, TaskStatus
from src.dna.loader import DNALoader


class DNAQuery:
    """Query DNA without exposing raw mutation."""

    def __init__(self, loader: DNALoader) -> None:
        self.loader = loader
        self._dna: dict[str, Any] | None = None

    def refresh(self) -> dict[str, Any]:
        self._dna = self.loader.load(force_reload=True)
        return self._dna

    def _data(self) -> dict[str, Any]:
        if self._dna is None:
            self.refresh()
        assert self._dna is not None
        return self._dna

  # --- Phase queries ---

    def get_current_phase(self) -> dict[str, Any] | None:
        dna = self._data()
        idx = dna.get("master_plan", {}).get("current_phase", 1)
        phases = dna.get("master_plan", {}).get("phase_sequence", [])
        if 1 <= idx <= len(phases):
            return phases[idx - 1]
        return None

    def get_phase_by_id(self, phase_id: str) -> dict[str, Any] | None:
        for p in self._data().get("master_plan", {}).get("phase_sequence", []):
            if isinstance(p, dict) and p.get("id") == phase_id:
                return p
        return None

    def get_phases_by_status(self, status: str | PhaseStatus) -> list[dict[str, Any]]:
        val = status.value if isinstance(status, PhaseStatus) else status
        return [
            p
            for p in self._data().get("master_plan", {}).get("phase_sequence", [])
            if isinstance(p, dict) and p.get("status") == val
        ]

    def get_blocked_phases(self) -> list[dict[str, Any]]:
        return self.get_phases_by_status(PhaseStatus.BLOCKED)

    def get_next_executable_phase(self) -> dict[str, Any] | None:
        phases = self._data().get("master_plan", {}).get("phase_sequence", [])
        completed = {
            p["id"]
            for p in phases
            if isinstance(p, dict) and p.get("status") == PhaseStatus.COMPLETED.value
        }
        for p in phases:
            if not isinstance(p, dict):
                continue
            if p.get("status") != PhaseStatus.NOT_STARTED.value:
                continue
            deps = set(p.get("dependencies", []))
            if deps <= completed:
                return p
        return None

    def get_incomplete_phases(self) -> list[dict[str, Any]]:
        terminal = {PhaseStatus.COMPLETED.value, PhaseStatus.CANCELLED.value}
        return [
            p
            for p in self._data().get("master_plan", {}).get("phase_sequence", [])
            if isinstance(p, dict) and p.get("status") not in terminal
        ]

    def get_completed_phases(self) -> list[dict[str, Any]]:
        return self.get_phases_by_status(PhaseStatus.COMPLETED)

  # --- Sub-task queries ---

    def get_active_subtasks(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for p in self._data().get("master_plan", {}).get("phase_sequence", []):
            if not isinstance(p, dict):
                continue
            for st in p.get("sub_tasks", []):
                if (
                    isinstance(st, dict)
                    and st.get("status") == TaskStatus.IN_PROGRESS.value
                ):
                    enriched = dict(st)
                    enriched["phase_id"] = p.get("id")
                    enriched["phase_name"] = p.get("name")
                    result.append(enriched)
        return result

    def get_subtasks_for_phase(self, phase_id: str) -> list[dict[str, Any]]:
        phase = self.get_phase_by_id(phase_id)
        return list(phase.get("sub_tasks", [])) if phase else []

    def get_next_pending_subtask(self, phase_id: str) -> dict[str, Any] | None:
        for st in self.get_subtasks_for_phase(phase_id):
            if isinstance(st, dict) and st.get("status") == TaskStatus.PENDING.value:
                return st
        return None

  # --- Dependency queries ---

    def get_phases_depending_on(self, phase_id: str) -> list[dict[str, Any]]:
        return [
            p
            for p in self._data().get("master_plan", {}).get("phase_sequence", [])
            if isinstance(p, dict) and phase_id in p.get("dependencies", [])
        ]

    def get_phase_dependencies(self, phase_id: str) -> list[dict[str, Any]]:
        phase = self.get_phase_by_id(phase_id)
        if not phase:
            return []
        ids = phase.get("dependencies", [])
        return [self.get_phase_by_id(pid) for pid in ids if self.get_phase_by_id(pid)]

    def get_phase_blockers(self, phase_id: str) -> list[str]:
        blockers: list[str] = []
        phase = self.get_phase_by_id(phase_id)
        if not phase:
            return blockers
        for dep_id in phase.get("dependencies", []):
            dep = self.get_phase_by_id(dep_id)
            if dep and dep.get("status") != PhaseStatus.COMPLETED.value:
                blockers.append(f"Incomplete dependency: {dep_id}")
        for bid in phase.get("blocked_by", []):
            blockers.append(f"Explicit blocker: {bid}")
        return blockers

  # --- Architecture queries ---

    def get_operational_components(self) -> list[dict[str, Any]]:
        return self._nodes_by_type(ComponentStatus.OPERATIONAL.value)

    def get_in_development_components(self) -> list[dict[str, Any]]:
        return self._nodes_by_type(ComponentStatus.IN_DEVELOPMENT.value)

    def _nodes_by_type(self, node_type: str) -> list[dict[str, Any]]:
        return [
            n
            for n in self._data().get("architecture_graph", {}).get("nodes", [])
            if isinstance(n, dict) and n.get("type") == node_type
        ]

    def get_component_dependencies(self, node_id: str) -> list[str]:
        node = self._find_node(node_id)
        return list(node.get("dependencies", [])) if node else []

    def find_components_affected_by_file(self, file_path: str) -> list[dict[str, Any]]:
        norm = file_path.replace("\\", "/")
        return [
            n
            for n in self._data().get("architecture_graph", {}).get("nodes", [])
            if isinstance(n, dict)
            and any(norm in f.replace("\\", "/") for f in n.get("files", []))
        ]

  # --- Progress queries ---

    def calculate_project_completion(self) -> float:
        phases = self._data().get("master_plan", {}).get("phase_sequence", [])
        if not phases:
            return 0.0
        total_weight = sum(max(p.get("estimated_tokens", 1), 1) for p in phases if isinstance(p, dict))
        if total_weight == 0:
            return 0.0
        weighted = sum(
            self.calculate_phase_completion(p.get("id", "")) * max(p.get("estimated_tokens", 1), 1)
            for p in phases
            if isinstance(p, dict)
        )
        return round(weighted / total_weight, 2)

    def estimate_remaining_tokens(self) -> int:
        total = 0
        for p in self.get_incomplete_phases():
            est = p.get("estimated_tokens", 0)
            consumed = p.get("tokens_consumed", 0)
            total += max(0, est - consumed)
        return total

    def calculate_phase_completion(self, phase_id: str) -> float:
        phase = self.get_phase_by_id(phase_id)
        if not phase:
            return 0.0
        subs = phase.get("sub_tasks", [])
        if not subs:
            return float(phase.get("completion_score", 0))
        total_weight = sum(max(st.get("estimated_tokens", 1), 1) for st in subs if isinstance(st, dict))
        if total_weight == 0:
            return float(phase.get("completion_score", 0))
        weighted = sum(
            (st.get("progress", 0) / 100.0) * max(st.get("estimated_tokens", 1), 1)
            for st in subs
            if isinstance(st, dict)
        )
        return round(100.0 * weighted / total_weight, 2)

  # --- Feature queries ---

    def get_planned_features(self) -> list[dict[str, Any]]:
        return list(
            self._data().get("feature_registry", {}).get("planned_features", [])
        )

    def get_unintegrated_emergent_features(self) -> list[dict[str, Any]]:
        return [
            f
            for f in self._data().get("feature_registry", {}).get("emergent_features", [])
            if isinstance(f, dict) and f.get("status") != "integrated"
        ]

    def get_features_by_priority(self, priority: int) -> list[dict[str, Any]]:
        return [f for f in self.get_planned_features() if f.get("priority") == priority]

  # --- Session queries ---

    def get_most_recent_session(self) -> dict[str, Any] | None:
        sessions = self._data().get("sessions_index", [])
        if not sessions:
            return None
        return max(sessions, key=lambda s: s.get("ended_at", ""))

    def get_sessions_for_phase(self, phase_id: str) -> list[dict[str, Any]]:
        return [
            s
            for s in self._data().get("sessions_index", [])
            if isinstance(s, dict) and s.get("phase_id") == phase_id
        ]

    def get_session_by_id(self, session_id: int) -> dict[str, Any] | None:
        for s in self._data().get("sessions_index", []):
            if isinstance(s, dict) and s.get("session_id") == session_id:
                return s
        return None

    def get_sessions_in_range(
        self,
        start: datetime | str,
        end: datetime | str,
    ) -> list[dict[str, Any]]:
        start_s = start.isoformat() if isinstance(start, datetime) else start
        end_s = end.isoformat() if isinstance(end, datetime) else end
        return [
            s
            for s in self._data().get("sessions_index", [])
            if isinstance(s, dict)
            and start_s <= s.get("started_at", "") <= end_s
        ]

  # --- Insight queries ---

    def get_unapplied_insights(self) -> list[dict[str, Any]]:
        return [i for i in self._data().get("insights", []) if not i.get("applied")]

    def get_insights_by_type(self, insight_type: str) -> list[dict[str, Any]]:
        return [i for i in self._data().get("insights", []) if i.get("type") == insight_type]

    def get_high_confidence_insights(self, threshold: float = 0.8) -> list[dict[str, Any]]:
        return [
            i
            for i in self._data().get("insights", [])
            if i.get("confidence", 0) >= threshold
        ]

    def _find_node(self, node_id: str) -> dict[str, Any] | None:
        for n in self._data().get("architecture_graph", {}).get("nodes", []):
            if isinstance(n, dict) and n.get("id") == node_id:
                return n
        return None


__all__ = ["DNAQuery"]
