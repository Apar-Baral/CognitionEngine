from __future__ import annotations

from typing import Any

from cognition_engine.core.constants import APPROX_CHARS_PER_TOKEN, BOOTSTRAP_TOKEN_CAP


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // APPROX_CHARS_PER_TOKEN)


def truncate_to_token_cap(text: str, cap: int = BOOTSTRAP_TOKEN_CAP) -> str:
    max_chars = cap * APPROX_CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 80] + "\n\n... [truncated to fit bootstrap token cap]"


def compile_bootstrap_markdown(
    project_name: str,
    strategic_lines: list[str],
    tactical: dict[str, Any],
    last_session: str | None,
    avoid_items: list[dict[str, Any]],
    budget_info: dict[str, Any] | None = None,
) -> str:
    sections: list[str] = [
        "# Cognition Engine — Session Bootstrap",
        "",
        f"**Project:** {project_name}",
        "",
        "## Where you are",
        "",
        f"- **Phase:** {tactical.get('phase_id')} — {tactical.get('phase_name')}",
        f"- **Sub-task:** {tactical.get('sub_task_id')} — {tactical.get('sub_task_name')}",
        "",
        "### Next action",
        "",
        tactical.get("next_action") or "_Continue the current sub-task._",
        "",
    ]

    if tactical.get("phase_description"):
        sections.extend(["### Phase context", "", tactical["phase_description"], ""])

    if last_session:
        sections.extend(["## Last session", "", last_session, ""])

    if tactical.get("pending_sub_tasks"):
        sections.extend(
            [
                "## Remaining in this phase",
                "",
                *[f"- {n}" for n in tactical["pending_sub_tasks"]],
                "",
            ]
        )

    sections.extend(["## Master plan", "", *[f"- {line}" for line in strategic_lines], ""])

    if avoid_items:
        sections.append("## Avoid (past hallucinations / mistakes)")
        sections.append("")
        for item in avoid_items[:5]:
            sections.append(
                f"- **{item.get('category')}**: `{item.get('proposed')}` → use `{item.get('correct')}`"
            )
        sections.append("")

    if budget_info:
        used = budget_info.get("tokens_consumed", 0)
        total = budget_info.get("session_budget_tokens", 0)
        zone = budget_info.get("zone", "green")
        sections.extend(
            [
                "## Session budget",
                "",
                f"- Used: {used:,} / {total:,} tokens ({zone} zone)",
                "",
            ]
        )

    sections.extend(
        [
            "## Rules",
            "",
            "- Do not re-read files marked understood unless asked.",
            "- Complete the current sub-task before starting unrelated work.",
            "- Run `ce end --summary \"...\"` when finishing this session.",
            "",
        ]
    )

    return truncate_to_token_cap("\n".join(sections))
