from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from cognition_engine.core.constants import PhaseStatus, SubTaskStatus


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DnaMutator:
    def __init__(self, dna: dict[str, Any]) -> None:
        self.dna = dna

    def set_phases(self, phases: list[dict[str, Any]]) -> None:
        self.dna["master_plan"]["phases"] = phases
        if phases and not self.dna.get("current_phase_id"):
            self.dna["current_phase_id"] = phases[0]["id"]
            subs = phases[0].get("sub_tasks", [])
            if subs:
                self.dna["current_sub_task_id"] = subs[0]["id"]

    def start_session(self, session_type: str = "BUILD") -> str:
        session_id = f"SES_{uuid4().hex[:8].upper()}"
        self.dna.setdefault("budget", {})["session_type"] = session_type
        self.dna["budget"]["tokens_consumed_this_session"] = 0
        return session_id

    def end_session(
        self,
        session_id: str,
        summary: str,
        files_modified: list[str] | None = None,
        tokens_used: int = 0,
        sub_task_completed: bool = False,
    ) -> None:
        phase = self._current_phase()
        sub_id = self.dna.get("current_sub_task_id")
        entry = {
            "id": session_id,
            "ended_at": _utc_now(),
            "summary": summary,
            "phase_id": self.dna.get("current_phase_id"),
            "sub_task_id": sub_id,
            "files_modified": files_modified or [],
            "tokens_used": tokens_used,
        }
        self.dna.setdefault("sessions_index", []).append(entry)

        budget = self.dna.setdefault("budget", {})
        budget["tokens_consumed_this_session"] = (
            budget.get("tokens_consumed_this_session", 0) + tokens_used
        )

        if sub_task_completed and phase and sub_id:
            for st in phase.get("sub_tasks", []):
                if st["id"] == sub_id:
                    st["status"] = SubTaskStatus.COMPLETED.value
                    st["progress"] = 100
                    break
            self._advance_sub_task(phase)

    def add_tokens(self, count: int) -> None:
        budget = self.dna.setdefault("budget", {})
        budget["tokens_consumed_this_session"] = (
            budget.get("tokens_consumed_this_session", 0) + count
        )

    def set_session_budget(self, tokens: int, session_type: str | None = None) -> None:
        budget = self.dna.setdefault("budget", {})
        budget["session_budget_tokens"] = tokens
        if session_type:
            budget["session_type"] = session_type

    def add_avoid_entry(
        self,
        category: str,
        proposed: str,
        correct: str,
        context: str = "",
    ) -> None:
        self.dna.setdefault("avoid_registry", []).append(
            {
                "id": f"AVD_{uuid4().hex[:6].upper()}",
                "category": category,
                "proposed": proposed,
                "correct": correct,
                "context": context,
                "recorded_at": _utc_now(),
            }
        )

    def _current_phase(self) -> dict[str, Any] | None:
        pid = self.dna.get("current_phase_id")
        for p in self.dna.get("master_plan", {}).get("phases", []):
            if p["id"] == pid:
                return p
        return None

    def _advance_sub_task(self, phase: dict[str, Any]) -> None:
        subs = phase.get("sub_tasks", [])
        for i, st in enumerate(subs):
            if st["status"] != SubTaskStatus.COMPLETED.value:
                st["status"] = SubTaskStatus.IN_PROGRESS.value
                self.dna["current_sub_task_id"] = st["id"]
                return
        phase["status"] = PhaseStatus.COMPLETED.value
        phase["completion_score"] = 100
        phases = self.dna["master_plan"]["phases"]
        idx = next(i for i, p in enumerate(phases) if p["id"] == phase["id"])
        if idx + 1 < len(phases):
            nxt = phases[idx + 1]
            nxt["status"] = PhaseStatus.IN_PROGRESS.value
            self.dna["current_phase_id"] = nxt["id"]
            for st in nxt.get("sub_tasks", []):
                if st["status"] != SubTaskStatus.COMPLETED.value:
                    st["status"] = SubTaskStatus.IN_PROGRESS.value
                    self.dna["current_sub_task_id"] = st["id"]
                    break
        else:
            self.dna["current_sub_task_id"] = None
