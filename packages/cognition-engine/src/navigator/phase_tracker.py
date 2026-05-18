"""
Phase state machine — progress tracking and validated transitions.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from src.core.constants import PhaseStatus, TaskStatus, VALID_PHASE_TRANSITIONS
from src.core.exceptions import InvalidTransitionError, TransitionBlockedError
from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery
from src.memory.session_tokens import session_tokens_consumed

VelocityTrend = Literal["accelerating", "stable", "decelerating"]


class PhaseTracker:
    """Manage phase transitions and progress metrics."""

    def __init__(self, query: DNAQuery, mutator: DNAMutator) -> None:
        self.query = query
        self.mutator = mutator

    def transition_phase(
        self,
        phase_id: str,
        new_status: str | PhaseStatus,
        *,
        session_id: int = 0,
        reason: str = "",
    ) -> dict[str, Any]:
        """Validate and apply a phase status transition."""
        phase = self.query.get_phase_by_id(phase_id)
        if not phase:
            raise InvalidTransitionError(
                f"Unknown phase {phase_id}",
                current_state="",
                attempted_state=str(new_status),
            )
        target = PhaseStatus(new_status.value if isinstance(new_status, PhaseStatus) else new_status)
        current = PhaseStatus(phase["status"])
        allowed = VALID_PHASE_TRANSITIONS.get(current, frozenset())
        if target not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition {phase_id} from {current.value} to {target.value}",
                current_state=current.value,
                attempted_state=target.value,
                valid_options=[s.value for s in allowed],
            )

        if target == PhaseStatus.COMPLETED:
            blockers = self._completion_blockers(phase)
            if blockers:
                raise TransitionBlockedError(
                    f"Cannot complete {phase_id}",
                    blockers=blockers,
                )

        return self.mutator.update_phase_status(phase_id, target, session_id, reason)

    def _completion_blockers(self, phase: dict[str, Any]) -> list[str]:
        blockers: list[str] = []
        for st in phase.get("sub_tasks", []):
            if st.get("status") != TaskStatus.DONE.value:
                blockers.append(f"Sub-task {st.get('id')} is not DONE")
        for dep_id in phase.get("dependencies", []):
            dep = self.query.get_phase_by_id(dep_id)
            if dep and dep.get("status") != PhaseStatus.COMPLETED.value:
                blockers.append(f"Dependency {dep_id} not completed")
        deliverables = phase.get("deliverables", [])
        if deliverables and phase.get("completion_score", 0) < 100:
            blockers.append("Deliverables not confirmed")
        return blockers

    def calculate_phase_progress(self, phase_id: str) -> float:
        """Weighted average of sub-task progress (by estimated_tokens)."""
        phase = self.query.get_phase_by_id(phase_id)
        if not phase:
            return 0.0
        subs = phase.get("sub_tasks", [])
        if not subs:
            return float(phase.get("completion_score", 0))
        total_weight = 0
        weighted = 0.0
        for st in subs:
            w = int(st.get("estimated_tokens") or 1)
            total_weight += w
            weighted += w * float(st.get("progress", 0))
        return weighted / total_weight if total_weight else 0.0

    def update_subtask_progress(
        self,
        phase_id: str,
        subtask_id: str,
        progress: int,
        status: str | TaskStatus | None = None,
    ) -> dict[str, Any]:
        """Update sub-task and recalculate phase completion_score."""
        dna = self.mutator.update_subtask_progress(phase_id, subtask_id, progress, status)

        def apply(d: dict[str, Any]) -> None:
            phase = next(
                (
                    p
                    for p in d.get("master_plan", {}).get("phase_sequence", [])
                    if isinstance(p, dict) and p.get("id") == phase_id
                ),
                None,
            )
            if phase:
                phase["completion_score"] = int(self.calculate_phase_progress(phase_id))

        self.mutator._mutate("sync_phase_progress", apply)
        return dna

    def get_phase_velocity(self, weeks: int = 4) -> tuple[float, VelocityTrend]:
        """Phases completed per week over the lookback window."""
        phases = self.query.get_completed_phases()
        cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        recent = []
        for p in phases:
            completed = p.get("completed")
            if not completed:
                continue
            try:
                dt = datetime.fromisoformat(str(completed))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= cutoff:
                    recent.append(dt)
            except ValueError:
                continue
        velocity = len(recent) / max(weeks, 1)
        mid = cutoff + timedelta(weeks=weeks // 2)
        first_half = sum(1 for d in recent if d < mid)
        second_half = len(recent) - first_half
        if second_half > first_half * 1.2:
            trend: VelocityTrend = "accelerating"
        elif second_half < first_half * 0.8:
            trend = "decelerating"
        else:
            trend = "stable"
        return velocity, trend

    def predict_completion_date(
        self,
        critical_path_phase_ids: list[str] | None = None,
    ) -> tuple[date, str]:
        """Estimate project completion from velocity and critical path."""
        velocity, _ = self.get_phase_velocity()
        phases = self.query._data().get("master_plan", {}).get("phase_sequence", [])
        remaining_ids = set(critical_path_phase_ids or [p["id"] for p in phases if isinstance(p, dict)])
        remaining = [
            p
            for p in phases
            if isinstance(p, dict)
            and p.get("id") in remaining_ids
            and p.get("status") != PhaseStatus.COMPLETED.value
        ]
        if not remaining:
            return date.today(), "high"
        weeks_needed = len(remaining) / max(velocity, 0.25)
        eta = date.today() + timedelta(weeks=weeks_needed)
        confidence = "high" if velocity >= 1.0 else "medium" if velocity >= 0.5 else "low"
        return eta, confidence

    def get_bottleneck_analysis(self) -> list[dict[str, Any]]:
        """Phases exceeding estimates, sorted by severity."""
        results: list[dict[str, Any]] = []
        for p in self.query._data().get("master_plan", {}).get("phase_sequence", []):
            if not isinstance(p, dict):
                continue
            est = int(p.get("estimated_tokens") or 1)
            actual = session_tokens_consumed(p)
            est_sessions = max(1, est // 10000)
            actual_sessions = int(p.get("sessions_used") or 0)
            ratio = max(actual / est, actual_sessions / est_sessions)
            if ratio <= 1.1:
                continue
            dependents = self.query.get_phases_depending_on(p["id"])
            results.append(
                {
                    "phase_id": p["id"],
                    "name": p.get("name"),
                    "severity": ratio,
                    "token_overrun_pct": (actual - est) / est * 100,
                    "dependent_count": len(dependents),
                }
            )
        return sorted(results, key=lambda x: -x["severity"])

    def record_progress(
        self,
        session_id: int,
        *,
        phase_id: str | None = None,
        tokens: int = 0,
    ) -> dict[str, Any]:
        """Update phase metrics after a session ends."""
        pid = phase_id or (self.query.get_current_phase() or {}).get("id")
        if not pid:
            return self.query.refresh()

        progress = int(self.calculate_phase_progress(pid))

        def apply(d: dict[str, Any]) -> None:
            phase = next(
                (
                    p
                    for p in d.get("master_plan", {}).get("phase_sequence", [])
                    if isinstance(p, dict) and p.get("id") == pid
                ),
                None,
            )
            if phase:
                phase["completion_score"] = progress
                phase["sessions_used"] = int(phase.get("sessions_used", 0)) + 1
                phase["tokens_consumed"] = session_tokens_consumed(phase) + tokens
            proj = d.get("project", {})
            proj["total_sessions"] = int(proj.get("total_sessions", 0)) + 1
            proj["total_tokens_consumed"] = int(proj.get("total_tokens_consumed", 0)) + tokens
            proj["last_updated"] = datetime.now(timezone.utc).isoformat()

        return self.mutator._mutate("record_progress", apply)
