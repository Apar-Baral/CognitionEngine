from __future__ import annotations

from typing import Any

from cognition_engine.core.constants import PhaseStatus


class StrategicMemory:
    """Project-level memory: phases, completion, velocity."""

    def __init__(self, dna: dict[str, Any]) -> None:
        self.dna = dna

    def completion_percentage(self) -> float:
        phases = self.dna.get("master_plan", {}).get("phases", [])
        if not phases:
            return 0.0
        done = sum(1 for p in phases if p.get("status") == PhaseStatus.COMPLETED.value)
        return round(100.0 * done / len(phases), 1)

    def current_phase(self) -> dict[str, Any] | None:
        pid = self.dna.get("current_phase_id")
        for p in self.dna.get("master_plan", {}).get("phases", []):
            if p["id"] == pid:
                return p
        return None

    def phase_summary_lines(self) -> list[str]:
        lines: list[str] = []
        for p in self.dna.get("master_plan", {}).get("phases", []):
            icon = {
                PhaseStatus.COMPLETED.value: "[x]",
                PhaseStatus.IN_PROGRESS.value: "[>]",
                PhaseStatus.BLOCKED.value: "[!]",
            }.get(p.get("status", PhaseStatus.PENDING.value), "[ ]")
            lines.append(f"{icon} {p['id']}: {p.get('name', '')}")
        return lines

    def last_session_summary(self) -> str | None:
        sessions = self.dna.get("sessions_index", [])
        if not sessions:
            return None
        return sessions[-1].get("summary")

    def total_tokens_consumed(self) -> int:
        return sum(s.get("tokens_used", 0) for s in self.dna.get("sessions_index", []))
