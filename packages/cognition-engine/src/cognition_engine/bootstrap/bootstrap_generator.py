from __future__ import annotations

from pathlib import Path
from typing import Any

from cognition_engine.bootstrap.context_compiler import compile_bootstrap_markdown, estimate_tokens
from cognition_engine.core.paths import cognition_dir
from cognition_engine.core.types import BootstrapPacket
from cognition_engine.memory.strategic_memory import StrategicMemory
from cognition_engine.memory.tactical_memory import TacticalMemory
from cognition_engine.token.budget_tracker import BudgetTracker


class BootstrapGenerator:
    def __init__(self, root: Path, dna: dict[str, Any]) -> None:
        self.root = root
        self.dna = dna

    def generate(self) -> BootstrapPacket:
        strategic = StrategicMemory(self.dna)
        tactical = TacticalMemory(self.dna)
        tracker = BudgetTracker(self.dna)

        avoid = self.dna.get("avoid_registry", [])[-5:]
        budget = self.dna.get("budget", {})
        used = budget.get("tokens_consumed_this_session", 0)
        total = budget.get("session_budget_tokens", 75_000)

        markdown = compile_bootstrap_markdown(
            project_name=self.dna["project"]["name"],
            strategic_lines=strategic.phase_summary_lines(),
            tactical=tactical.active_phase_context(),
            last_session=strategic.last_session_summary(),
            avoid_items=avoid,
            budget_info={
                "tokens_consumed": used,
                "session_budget_tokens": total,
                "zone": tracker.zone(used, total).value,
            },
        )

        packet = BootstrapPacket(
            markdown=markdown,
            metadata={
                "phase_id": self.dna.get("current_phase_id"),
                "sub_task_id": self.dna.get("current_sub_task_id"),
                "estimated_tokens": estimate_tokens(markdown),
            },
            estimated_tokens=estimate_tokens(markdown),
        )
        packet.write_files(cognition_dir(self.root))
        return packet
