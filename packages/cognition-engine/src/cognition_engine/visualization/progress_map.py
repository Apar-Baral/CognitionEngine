from __future__ import annotations

from typing import Any

from cognition_engine.memory.strategic_memory import StrategicMemory


def render_progress_map(dna: dict[str, Any], width: int = 50) -> str:
    strategic = StrategicMemory(dna)
    pct = strategic.completion_percentage()
    filled = int(width * pct / 100)
    bar = "=" * filled + "-" * (width - filled)

    lines = [
        "",
        "  COGNITION ENGINE — Progress",
        f"  Project: {dna.get('project', {}).get('name', '?')}",
        f"  [{bar}] {pct}%",
        "",
    ]
    lines.extend(f"  {line}" for line in strategic.phase_summary_lines())
    phase = strategic.current_phase()
    if phase:
        sub = dna.get("current_sub_task_id")
        lines.extend(["", f"  >> Active: {phase['id']} / {sub or '—'}", ""])
    return "\n".join(lines)
