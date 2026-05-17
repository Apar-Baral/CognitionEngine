"""
Permanent project-level memory (strategic tier).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

import networkx as nx

from src.core.constants import PhaseStatus, TaskStatus
from src.dna.query import DNAQuery


class StrategicMemory:
    """Project-wide awareness built on DNAQuery."""

    STUCK_SESSION_THRESHOLD = 5
    LONG_CHAIN_THRESHOLD = 8

    def __init__(self, query: DNAQuery) -> None:
        self.query = query

    def get_project_summary(self) -> dict[str, Any]:
        dna = self.query.refresh()
        proj = dna.get("project", {})
        current = self.query.get_current_phase()
        phases = dna.get("master_plan", {}).get("phase_sequence", [])
        completed = self.query.get_completed_phases()
        incomplete = self.query.get_incomplete_phases()
        return {
            "project_name": proj.get("name", ""),
            "version": proj.get("version", ""),
            "overall_completion_percentage": self.query.calculate_project_completion(),
            "current_phase_id": current.get("id") if current else None,
            "current_phase_name": current.get("name") if current else None,
            "total_sessions": proj.get("total_sessions", 0),
            "total_tokens_consumed": proj.get("total_tokens_consumed", 0),
            "total_hallucinations_caught": proj.get("total_hallucinations_caught", 0),
            "total_tokens_saved": proj.get("total_tokens_saved", 0),
            "completed_phases_count": len(completed),
            "remaining_phases_count": len(incomplete),
            "total_phases": len(phases),
        }

    def get_current_state(self) -> dict[str, Any]:
        phase = self.query.get_current_phase()
        if not phase:
            return {"active": False}
        active_subs = [
            st
            for st in phase.get("sub_tasks", [])
            if isinstance(st, dict)
            and st.get("status") == TaskStatus.IN_PROGRESS.value
        ]
        files_modified: list[str] = []
        for st in phase.get("sub_tasks", []):
            if isinstance(st, dict):
                files_modified.extend(st.get("files_modified", []))
        return {
            "active": True,
            "phase_id": phase.get("id"),
            "name": phase.get("name"),
            "description": phase.get("description"),
            "completion_percentage": self.query.calculate_phase_completion(phase["id"]),
            "active_sub_tasks": active_subs,
            "all_sub_tasks": phase.get("sub_tasks", []),
            "files_being_modified": list(dict.fromkeys(files_modified)),
            "recent_decisions": phase.get("state_history", [])[-5:],
            "blockers": self.query.get_phase_blockers(phase["id"]),
        }

    def get_critical_path(self) -> list[str]:
        phases = self.query._data().get("master_plan", {}).get("phase_sequence", [])
        if not phases:
            return []
        g: nx.DiGraph = nx.DiGraph()
        for p in phases:
            if not isinstance(p, dict):
                continue
            pid = p["id"]
            weight = max(p.get("estimated_tokens", 1), 1)
            g.add_node(pid, weight=weight)
            for dep in p.get("dependencies", []):
                dep_phase = self.query.get_phase_by_id(dep)
                w = max(dep_phase.get("estimated_tokens", 1), 1) if dep_phase else 1
                g.add_edge(dep, pid, weight=w)
        if not nx.is_directed_acyclic_graph(g):
            return [p["id"] for p in phases if isinstance(p, dict)]
        try:
            path = nx.dag_longest_path(g, weight="weight")
            return list(path)
        except nx.NetworkXError:
            return [p["id"] for p in phases if isinstance(p, dict)]

    def get_next_actions(self) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        phase = self.query.get_current_phase()
        if phase:
            for st in phase.get("sub_tasks", []):
                if not isinstance(st, dict):
                    continue
                if st.get("status") in (
                    TaskStatus.IN_PROGRESS.value,
                    TaskStatus.PENDING.value,
                ):
                    actions.append(
                        {
                            "priority": 1,
                            "phase_id": phase["id"],
                            "sub_task_id": st.get("id"),
                            "description": st.get("next_action") or st.get("name", ""),
                            "estimated_tokens": st.get("estimated_tokens", 5000),
                        }
                    )
        nxt = self.query.get_next_executable_phase()
        if nxt and (not phase or nxt["id"] != phase.get("id")):
            actions.append(
                {
                    "priority": 2,
                    "phase_id": nxt["id"],
                    "description": f"Start phase: {nxt.get('name')}",
                    "estimated_tokens": nxt.get("estimated_tokens", 10000),
                }
            )
        for blocked in self.query.get_blocked_phases():
            actions.append(
                {
                    "priority": 3,
                    "phase_id": blocked["id"],
                    "description": f"Unblock phase: {blocked.get('name')}",
                    "estimated_tokens": 2000,
                    "blockers": self.query.get_phase_blockers(blocked["id"]),
                }
            )
        return sorted(actions, key=lambda a: a["priority"])

    def snapshot(self) -> tuple[dict[str, Any], str]:
        ts = datetime.now(timezone.utc).isoformat()
        return copy.deepcopy(self.query.refresh()), ts

    def validate_project_health(self) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        dna = self.query._data()
        sessions = dna.get("sessions_index", [])
        proj_sessions = dna.get("project", {}).get("total_sessions", 0)
        if proj_sessions != len(sessions):
            warnings.append(
                {
                    "code": "session_count_mismatch",
                    "message": (
                        f"project.total_sessions ({proj_sessions}) != "
                        f"sessions_index length ({len(sessions)})"
                    ),
                    "severity": "high",
                }
            )

        for phase in dna.get("master_plan", {}).get("phase_sequence", []):
            if not isinstance(phase, dict):
                continue
            if phase.get("status") == PhaseStatus.IN_PROGRESS.value:
                used = phase.get("sessions_used", 0)
                if used >= self.STUCK_SESSION_THRESHOLD:
                    warnings.append(
                        {
                            "code": "phase_stuck",
                            "message": (
                                f"{phase['id']} IN_PROGRESS for {used} sessions"
                            ),
                            "severity": "medium",
                        }
                    )

        critical = self.get_critical_path()
        if len(critical) > self.LONG_CHAIN_THRESHOLD:
            warnings.append(
                {
                    "code": "long_dependency_chain",
                    "message": f"Critical path length {len(critical)} exceeds threshold",
                    "severity": "low",
                }
            )

        completion = self.query.calculate_project_completion()
        if proj_sessions > 0 and completion < 5 and len(sessions) > 3:
            warnings.append(
                {
                    "code": "low_completion_high_sessions",
                    "message": (
                        f"Completion {completion}% with {proj_sessions} sessions"
                    ),
                    "severity": "medium",
                }
            )

        for phase in self.query.get_blocked_phases():
            blockers = phase.get("blocked_by", [])
            if len(blockers) > 0 and phase.get("sessions_used", 0) > self.STUCK_SESSION_THRESHOLD:
                warnings.append(
                    {
                        "code": "persistent_blocker",
                        "message": (
                            f"{phase['id']} blocked for >{self.STUCK_SESSION_THRESHOLD} "
                            f"sessions: {blockers}"
                        ),
                        "severity": "high",
                    }
                )

        return warnings

    def get_phase_history(self) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for phase in self.query.get_completed_phases():
            sessions = self.query.get_sessions_for_phase(phase["id"])
            history.append(
                {
                    "phase_id": phase["id"],
                    "name": phase.get("name"),
                    "completed": phase.get("completed"),
                    "sessions_used": phase.get("sessions_used", len(sessions)),
                    "tokens_consumed": phase.get("tokens_consumed", 0),
                    "session_ids": [s.get("session_id") for s in sessions],
                }
            )
        return sorted(history, key=lambda h: h.get("completed") or "")
