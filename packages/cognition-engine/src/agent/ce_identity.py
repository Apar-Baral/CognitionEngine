"""Truthful Cognition Engine platform identity for LLM system prompts."""

from __future__ import annotations

from typing import Any


def ce_platform_identity(ctx: Any | None = None) -> str:
    """Describe real CE subsystems so the model does not deny implemented features."""
    lines = [
        "## Cognition Engine platform (you are part of this — not a generic chatbot)",
        "Cognition Engine is an AI development orchestrator with these **implemented** subsystems:",
        "",
        "**Planner / progress** — Master plan in project DNA (phases, milestones). "
        "Commands: /plan, /showplan, /status. UI: Generate plan, Show plan, Track progress.",
        "",
        "**Hallucination Shield** — Static analysis + truth database; blocks invalid Python on "
        "agent write_file and via `cognition-engine validate`. Logged to DNA on /end.",
        "",
        "**Memory** — Per-session operational memory; vector store for session summaries; "
        "tactical memory; /memory and /end persist insights to project DNA.",
        "",
        "**Reinforcement learning** — Q-learning token allocator records session outcomes on /end "
        "and recommends BUILD/REVIEW token budgets.",
        "",
        "**Token optimization** — Session token budgets, live token bar in UI, API usage logging, "
        "budget enforcer in proxy layer, RL-adjusted allocation.",
        "",
        "When users ask about planning, shield, memory, RL, or tokens: explain how **CE** provides them. "
        "Never say you are 'only a single assistant without those subsystems'.",
        "For meta questions, mention relevant slash commands and sidebar actions.",
    ]
    if ctx is not None:
        try:
            if ctx.is_initialized():
                hall = int(
                    ctx.query.refresh().get("project", {}).get(
                        "total_hallucinations_caught", 0
                    )
                )
                sens = ctx.config.get("shield_sensitivity", "medium")
                lines.append(
                    f"\n**This project:** shield={sens}, hallucinations caught in DNA={hall}."
                )
            else:
                lines.append("\n**This folder:** CE project not initialized — suggest Setup keys or /setup.")
        except Exception:
            pass
    return "\n".join(lines)
