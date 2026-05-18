"""Assemble system context for agent turns."""

from __future__ import annotations

from pathlib import Path

from src.cli.context import ProjectContext


class ContextAssembler:
    def __init__(self, ctx: ProjectContext) -> None:
        self.ctx = ctx

    def build_system_prompt(self) -> str:
        parts: list[str] = [
            "You are Cognition Engine, an AI development assistant with guardrails.",
            "Stay on the active phase and project goal. Prefer small, testable changes.",
        ]
        goal = self.ctx.get_project_goal()
        if goal:
            parts.append(f"\n## Project goal\n{goal}")
        boot = self.ctx.cognition_dir / "bootstrap.md"
        if boot.is_file():
            text = boot.read_text(encoding="utf-8")
            if len(text) > 8000:
                text = text[:8000] + "\n…(truncated)"
            parts.append(f"\n## Session bootstrap\n{text}")
        try:
            from src.memory.vector_store import VectorMemoryStore

            store = VectorMemoryStore(self.ctx.root, self.ctx.project_name())
            hits = store.search("sessions", goal or "current task", n=3)
            if hits:
                parts.append("\n## Recent memory")
                for h in hits:
                    parts.append(f"- {h.get('document', '')[:300]}")
        except Exception:
            pass
        return "\n".join(parts)
