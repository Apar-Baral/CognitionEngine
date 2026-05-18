"""Assemble system context for agent turns."""

from __future__ import annotations

from pathlib import Path

from src.cli.context import ProjectContext


class ContextAssembler:
    def __init__(self, ctx: ProjectContext) -> None:
        self.ctx = ctx

    def build_system_prompt(self) -> str:
        parts: list[str] = [
            "You are Cognition Engine, an autonomous coding agent with real tools.",
            "You can write files, list directories, and run shell commands on the user's project.",
            "Execute tools until the user's request is complete — do not only describe plans.",
            f"Project root: {self.ctx.root}",
            "Stay on the active phase and project goal.",
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

    def build_quick_prompt(self) -> str:
        """Light system prompt for conversational / simple Q&A (no tools)."""
        parts = [
            "You are Cognition Engine, a helpful coding assistant.",
            "Answer clearly and concisely. Do not use tools or JSON tool syntax.",
            "Do not output DSML or XML tool blocks — plain markdown only.",
            f"Project: {self.ctx.root}",
        ]
        goal = self.ctx.get_project_goal()
        if goal:
            parts.append(f"Goal: {goal[:400]}")
        return "\n".join(parts)
