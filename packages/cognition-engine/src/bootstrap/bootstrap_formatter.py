"""
Format gathered bootstrap data into the canonical session bootstrap layout.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.bootstrap.context_compiler import estimate_tokens
from src.core.constants import BOOTSTRAP_MAX_TOKENS

BOX_WIDTH = 62

@dataclass
class BootstrapParts:
    """Inputs for the canonical bootstrap template."""

    session_id: str = "PREVIEW"
    phase_id: str = ""
    phase_name: str = ""
    phase_completion: float = 0.0
    subtask_id: str = ""
    subtask_name: str = ""
    subtask_progress: int = 0
    objective: str = ""
    project_goal: str = ""
    previous_session_id: str = ""
    last_completed: str = ""
    last_decisions: list[str] = field(default_factory=list)
    last_files_modified: list[str] = field(default_factory=list)
    last_unfinished: str = ""
    relevant_files: list[tuple[str, str]] = field(default_factory=list)
    avoid_items: list[str] = field(default_factory=list)
    predicted_tokens: int = 0
    recommended_budget: int = 0
    cost_estimate: float = 0.0
    supplementary: str = ""


def format_bootstrap(parts: BootstrapParts, max_tokens: int = BOOTSTRAP_MAX_TOKENS) -> str:
    """Render the spec bootstrap layout, trimming optional sections to fit budget."""
    sid = parts.session_id or "PREVIEW"
    header_title = f" COGNITION ENGINE — SESSION #{sid} "

    lines: list[str] = [
        "╔" + "═" * BOX_WIDTH + "╗",
        "║" + header_title.center(BOX_WIDTH) + "║",
        "╚" + "═" * BOX_WIDTH + "╝",
        "",
        "📋 CURRENT MISSION",
        (
            f"Phase {parts.phase_id}: {parts.phase_name} — "
            f"{parts.phase_completion}% complete"
        ),
        (
            f"Active: {parts.subtask_id} — {parts.subtask_name} "
            f"({parts.subtask_progress}% done)"
        ),
        f"Objective: {parts.objective}",
        "",
    ]
    if parts.project_goal:
        lines.extend(
            [
                "🎯 PROJECT GOAL (full)",
                parts.project_goal.strip(),
                "",
            ]
        )

    prev = parts.previous_session_id or "—"
    lines.extend(
        [
            f"📝 LAST SESSION (Session #{prev})",
            f"Completed: {parts.last_completed or '—'}",
            f"Decisions: {'; '.join(parts.last_decisions) if parts.last_decisions else '—'}",
            f"Files Modified: {', '.join(parts.last_files_modified) if parts.last_files_modified else '—'}",
            f"Unfinished: {parts.last_unfinished or '—'}",
            "",
            "📂 RELEVANT FILES",
        ]
    )

    file_lines = parts.relevant_files
    avoid_lines = [f"• {item}" for item in parts.avoid_items]

    budget_block = [
        "",
        "💰 BUDGET",
        f"Predicted: {parts.predicted_tokens:,} tokens",
        f"Recommended Cap: {parts.recommended_budget:,} tokens",
        f"Estimated Cost: ${parts.cost_estimate:.2f}",
        "",
        "═══════════════════════════════════════════════════════════════",
        "Ready. Continue from where you left off.",
        "═══════════════════════════════════════════════════════════════",
    ]

    if parts.supplementary:
        budget_block.insert(0, parts.supplementary.rstrip())
        budget_block.insert(0, "")

    def render(files: list[tuple[str, str]], avoids: list[str]) -> str:
        body = list(lines)
        if files:
            for path, summary in files:
                body.append(f"{path} — {summary}")
        else:
            body.append("(none identified)")
        body.append("")
        body.append("⚠️ DO NOT REPEAT")
        if avoids:
            body.extend(avoids)
        else:
            body.append("• (none)")
        body.extend(budget_block)
        return "\n".join(body)

    text = render(file_lines, avoid_lines)
    if estimate_tokens(text) <= max_tokens:
        return text

    while file_lines and estimate_tokens(render(file_lines, avoid_lines)) > max_tokens:
        file_lines = file_lines[:-1]

    while avoid_lines and estimate_tokens(render(file_lines, avoid_lines)) > max_tokens:
        avoid_lines = avoid_lines[:-1]

    text = render(file_lines, avoid_lines)
    if estimate_tokens(text) > max_tokens and parts.supplementary:
        parts.supplementary = ""
        text = render(file_lines, avoid_lines)

    return text
