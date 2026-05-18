"""
Prioritized recommendations synthesizing navigator intelligence.
"""

from __future__ import annotations

from typing import Any

from src.core.constants import PhaseStatus, TaskStatus
from src.dna.query import DNAQuery
from src.navigator.complexity_forecaster import ComplexityForecaster
from src.navigator.debt_detector import DebtDetector
from src.navigator.dependency_resolver import DependencyResolver
from src.navigator.phase_tracker import PhaseTracker


class RecommendationEngine:
    """Actionable next-step guidance."""

    def __init__(
        self,
        tracker: PhaseTracker,
        resolver: DependencyResolver,
        forecaster: ComplexityForecaster,
        debt: DebtDetector,
        query: DNAQuery,
    ) -> None:
        self.tracker = tracker
        self.resolver = resolver
        self.forecaster = forecaster
        self.debt = debt
        self.query = query

    def get_recommendations(self, limit: int = 10) -> list[dict[str, Any]]:
        """Prioritized recommendations from all sources."""
        recs: list[dict[str, Any]] = []
        recs.extend(self._continue_current())
        recs.extend(self._unblock())
        recs.extend(self._start_next())
        recs.extend(self._pay_debt())
        recs.extend(self._optimize())
        recs.extend(self._address_risks())
        recs.sort(key=lambda r: -r.get("priority", 0))
        return recs[:limit]

    def get_next_session_prompt(self) -> str:
        """Human-readable next session suggestion."""
        recs = self.get_recommendations(limit=1)
        if recs:
            return recs[0].get("description", "Continue current work.")
        phase = self.query.get_current_phase()
        if not phase:
            return "Run `cognition-engine plan` to define phases, then `cognition-engine start`."
        st = next(
            (
                s
                for s in phase.get("sub_tasks", [])
                if s.get("status") in (TaskStatus.IN_PROGRESS.value, TaskStatus.PENDING.value)
            ),
            None,
        )
        if st:
            est = int(st.get("estimated_tokens", 12000) or 12000)
            remaining = int((100 - st.get("progress", 0)) / 100 * est)
            return (
                f"Next session: Continue {phase['id']} — {st.get('name', '')} "
                f"({st.get('progress', 0)}% done). Estimated: {remaining:,} tokens."
            )
        return f"Next session: Advance {phase['id']} — {phase.get('name', '')}."

    def get_daily_briefing(self) -> dict[str, Any]:
        """Comprehensive status for starting the day."""
        dna = self.query.refresh()
        project = dna.get("project", {})
        phases = dna.get("master_plan", {}).get("phase_sequence", [])
        completion = self.query.calculate_project_completion()
        cp = self.resolver.get_critical_path_progress()
        velocity, trend = self.tracker.get_phase_velocity()
        blockers = self.query.get_blocked_phases()
        top = self.get_recommendations(limit=3)
        return {
            "project": project.get("name"),
            "health": "good" if not blockers and completion > 0 else "attention",
            "completion_pct": completion,
            "critical_path_pct": cp.get("completion_pct", 0),
            "velocity_per_week": velocity,
            "velocity_trend": trend,
            "blockers": [p["id"] for p in blockers],
            "top_recommendations": top,
            "next_session": self.get_next_session_prompt(),
        }

    def _continue_current(self) -> list[dict[str, Any]]:
        phase = self.query.get_current_phase()
        if not phase or phase.get("status") != PhaseStatus.IN_PROGRESS.value:
            return []
        for st in phase.get("sub_tasks", []):
            if st.get("status") == TaskStatus.IN_PROGRESS.value:
                prog = st.get("progress", 0)
                est = int(st.get("estimated_tokens", 12000) or 12000)
                remaining = int(est * (100 - prog) / 100)
                return [
                    {
                        "type": "continue",
                        "priority": 10,
                        "description": (
                            f"Complete {phase['id']} sub-task {st['id']}: {st.get('name', '')}. "
                            f"{prog}% done, ~{remaining:,} tokens remaining."
                        ),
                        "rationale": "Incomplete work in the active phase should be finished first.",
                        "effort_tokens": remaining,
                        "impact": "high",
                    }
                ]
        return []

    def _unblock(self) -> list[dict[str, Any]]:
        recs = []
        path, _ = self.resolver.find_critical_path()
        for p in self.query.get_blocked_phases():
            blockers = self.resolver.find_blockers(p["id"])
            on_cp = p["id"] in path
            deps = self.resolver.what_depends_on(p["id"])
            recs.append(
                {
                    "type": "unblock",
                    "priority": 9 if on_cp else 7,
                    "description": (
                        f"Unblock {p['id']}: {p.get('name', '')}. "
                        f"Blocks {len(deps)} dependent phase(s)."
                    ),
                    "rationale": "; ".join(b["resolution"] for b in blockers[:2]) or "Resolve dependencies",
                    "effort_tokens": 20000,
                    "impact": "high" if on_cp else "medium",
                }
            )
        return recs

    def _start_next(self) -> list[dict[str, Any]]:
        phase = self.query.get_current_phase()
        if phase and phase.get("completion_score", 0) < 85:
            return []
        nxt = self.query.get_next_executable_phase()
        if not nxt:
            return []
        return [
            {
                "type": "start_next",
                "priority": 8,
                "description": f"Start {nxt['id']}: {nxt.get('name', '')}.",
                "rationale": "Current phase nearly complete; next executable phase is ready.",
                "effort_tokens": nxt.get("estimated_tokens", 15000),
                "impact": "high",
            }
        ]

    def _pay_debt(self) -> list[dict[str, Any]]:
        recs = []
        for item in self.debt.recommend_payoff_order(3):
            roi = self.debt.calculate_roi(item)
            if roi.get("roi_positive"):
                recs.append(
                    {
                        "type": "debt",
                        "priority": 6,
                        "description": (
                            f"Refactor {item['file_path']}:{item['line_number']} "
                            f"({item['type']}) — saves ~{item.get('expected_savings_per_session', 0):,} tok/session."
                        ),
                        "rationale": f"Age {item.get('age_days', 0)}d, severity {item.get('severity')}",
                        "effort_tokens": item.get("payoff_tokens", 15000),
                        "impact": "medium",
                    }
                )
        return recs

    def _optimize(self) -> list[dict[str, Any]]:
        history = self.query.refresh().get("sessions_index", [])
        if len(history) < 5:
            return []
        recent = [s.get("efficiency_score", 0.7) for s in history[-5:] if isinstance(s, dict)]
        if not recent:
            return []
        avg = sum(recent) / len(recent)
        older = [s.get("efficiency_score", 0.7) for s in history[-10:-5] if isinstance(s, dict)]
        if older and avg < sum(older) / len(older) * 0.85:
            return [
                {
                    "type": "optimize",
                    "priority": 5,
                    "description": (
                        "Session efficiency dropped ~15% over last 5 sessions. "
                        "Reduce context size or mark files as understood."
                    ),
                    "rationale": "Declining efficiency increases cost per deliverable.",
                    "effort_tokens": 5000,
                    "impact": "medium",
                }
            ]
        return []

    def _address_risks(self) -> list[dict[str, Any]]:
        recs = []
        try:
            hotspots = self.forecaster.identify_hotspots(3)
        except Exception:
            hotspots = []
        for h in hotspots:
            if h["lines"] > 1500:
                recs.append(
                    {
                        "type": "risk",
                        "priority": 7,
                        "description": (
                            f"Split {h['file']} ({h['lines']} lines) before complexity grows further."
                        ),
                        "rationale": "Large files correlate with higher hallucination rates.",
                        "effort_tokens": h.get("score", 50) * 200,
                        "impact": "high",
                    }
                )
        trend = self.forecaster.project_complexity_trend()
        if trend.get("trend") == "increasing":
            recs.append(
                {
                    "type": "risk",
                    "priority": 6,
                    "description": "Complexity is trending up — schedule a hardening/refactor session.",
                    "rationale": f"Projected CC: {trend.get('projected_2_weeks')}",
                    "effort_tokens": 25000,
                    "impact": "medium",
                }
            )
        return recs
