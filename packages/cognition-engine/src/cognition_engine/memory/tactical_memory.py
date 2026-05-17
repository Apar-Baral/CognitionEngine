from __future__ import annotations

from typing import Any


class TacticalMemory:
    """Per-phase context for bootstrap."""

    def __init__(self, dna: dict[str, Any]) -> None:
        self.dna = dna

    def current_sub_task(self) -> dict[str, Any] | None:
        pid = self.dna.get("current_phase_id")
        sid = self.dna.get("current_sub_task_id")
        for p in self.dna.get("master_plan", {}).get("phases", []):
            if p["id"] != pid:
                continue
            for st in p.get("sub_tasks", []):
                if st["id"] == sid:
                    return st
        return None

    def active_phase_context(self) -> dict[str, Any]:
        phase = None
        pid = self.dna.get("current_phase_id")
        for p in self.dna.get("master_plan", {}).get("phases", []):
            if p["id"] == pid:
                phase = p
                break
        sub = self.current_sub_task()
        return {
            "phase_id": pid,
            "phase_name": phase.get("name") if phase else None,
            "phase_description": phase.get("description") if phase else None,
            "sub_task_id": sub.get("id") if sub else None,
            "sub_task_name": sub.get("name") if sub else None,
            "next_action": sub.get("next_action") if sub else None,
            "pending_sub_tasks": [
                st["name"]
                for st in (phase or {}).get("sub_tasks", [])
                if st.get("status") != "completed"
            ],
        }
