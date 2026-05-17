"""
Compile raw project memory into a token-efficient bootstrap context block.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from src.core.constants import BOOTSTRAP_MAX_TOKENS
from src.memory.strategic_memory import StrategicMemory
from src.memory.tactical_memory import TacticalMemory

TOKEN_MULTIPLIER = 1.3
SECTION_RULE = "═" * 63
SECTION_MINOR = "─" * 63


def estimate_tokens(text: str) -> int:
    """Estimate tokens as word_count * 1.3."""
    words = len(text.split())
    if not text.strip():
        return 0
    return max(1, int(words * TOKEN_MULTIPLIER))


class ContextCompiler:
    """Build tiered bootstrap context within a token budget."""

    def __init__(
        self,
        strategic: StrategicMemory,
        tactical: TacticalMemory,
        project_root: Path | str | None = None,
    ) -> None:
        self.strategic = strategic
        self.tactical = tactical
        self.project_root = Path(project_root) if project_root else Path.cwd()

    def compile_context(
        self,
        task_description: str,
        max_tokens: int = BOOTSTRAP_MAX_TOKENS,
        *,
        avoid_items: list[dict[str, Any]] | None = None,
        last_session_files: list[str] | None = None,
        last_session_decisions: list[dict[str, Any]] | None = None,
        relevant_file_paths: list[str] | None = None,
        architecture_nodes: list[dict[str, Any]] | None = None,
        session_history_summary: str | None = None,
        project_root: Path | str | None = None,
    ) -> str:
        """Compile bootstrap context; Tier 1 is never dropped."""
        root = Path(project_root) if project_root else self.project_root
        state = self.strategic.get_current_state()
        tactical_ctx = self.tactical.get_active_context()
        avoid_items = avoid_items or []

        tier1_parts = self._build_tier1(
            state,
            tactical_ctx,
            task_description,
            avoid_items,
            last_session_files or [],
            last_session_decisions or [],
        )
        tier2_parts = self._build_tier2(
            state,
            tactical_ctx,
            relevant_file_paths or [],
            architecture_nodes or [],
            session_history_summary,
            root,
        )
        tier3_parts = self._build_tier3()

        sections: list[str] = [
            SECTION_RULE,
            "COGNITION ENGINE — SESSION BOOTSTRAP",
            SECTION_RULE,
            "",
        ]
        used = estimate_tokens("\n".join(sections))

        tier1_text = self._join_section("TIER 1 — WHERE YOU ARE (required)", tier1_parts)
        sections.append(tier1_text)
        used += estimate_tokens(tier1_text)

        budget_remaining = max_tokens - used
        tier2_text = self._fit_tier2(tier2_parts, budget_remaining)
        if tier2_text:
            sections.append(tier2_text)
            used += estimate_tokens(tier2_text)

        budget_remaining = max_tokens - used
        if budget_remaining > 80:
            tier3_text = self._join_section("TIER 3 — PROJECT OVERVIEW (optional)", tier3_parts)
            if estimate_tokens(tier3_text) <= budget_remaining:
                sections.append(tier3_text)
            elif tier3_parts:
                compressed = " | ".join(
                    line.replace("\n", " ") for part in tier3_parts for line in part.splitlines() if line
                )[:400]
                sections.append(
                    self._join_section(
                        "TIER 3 — PROJECT OVERVIEW (compressed)",
                        [compressed],
                    )
                )

        sections.extend(
            [
                "",
                SECTION_MINOR,
                "Complete the active sub-task before unrelated work.",
                "Run session end when finished so the next bootstrap stays accurate.",
                SECTION_MINOR,
            ]
        )
        return "\n".join(sections)

    def summarize_file(self, file_path: str | Path) -> str:
        """One-line summary from module docstring or header comments."""
        path = Path(file_path)
        if not path.is_file():
            resolved = self.project_root / path
            if resolved.is_file():
                path = resolved
            else:
                return f"{file_path}: (file not found)"

        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return f"{path.name}: (unreadable)"

        if path.suffix == ".py":
            doc = ast.get_docstring(ast.parse(text))
            if doc:
                first = doc.strip().splitlines()[0]
                return f"{path.as_posix()}: {first[:120]}"

        for line in text.splitlines()[:40]:
            stripped = line.strip()
            if stripped.startswith("#"):
                body = stripped.lstrip("#").strip()
                if body:
                    return f"{path.as_posix()}: {body[:120]}"
            if stripped.startswith("/*") or stripped.startswith("*"):
                body = stripped.strip("/*").strip()
                if body and body != "/":
                    return f"{path.as_posix()}: {body[:120]}"
            if stripped and not stripped.startswith("import"):
                break
        return f"{path.as_posix()}: ({path.suffix or 'file'} module)"

    def summarize_decision(self, decision: dict[str, Any]) -> str:
        """Compress a decision record to one line."""
        text = decision.get("decision") or decision.get("finding") or decision.get("reason", "")
        rationale = decision.get("rationale") or decision.get("reason", "")
        if rationale and rationale != text:
            return f"{text} — because: {rationale}"
        return str(text)

    @staticmethod
    def estimate_tokens(text: str) -> int:
        return estimate_tokens(text)

    def _build_tier1(
        self,
        state: dict[str, Any],
        tactical_ctx: dict[str, Any],
        task_description: str,
        avoid_items: list[dict[str, Any]],
        last_files: list[str],
        last_decisions: list[dict[str, Any]],
    ) -> list[str]:
        parts: list[str] = []
        if not state.get("active"):
            parts.append("No active phase — review master plan and start the next executable phase.")
            return parts

        phase_id = state.get("phase_id", "?")
        phase_name = state.get("name", "?")
        completion = state.get("completion_percentage", 0)
        parts.append(f"Phase: {phase_id} — {phase_name} ({completion}% complete)")

        active_sub = self._resolve_active_subtask(state, tactical_ctx)
        if active_sub:
            st_id = active_sub.get("id", "?")
            st_name = active_sub.get("name", "?")
            progress = active_sub.get("progress", 0)
            parts.append(f"Active sub-task: {st_id} — {st_name} ({progress}% progress)")
            next_action = active_sub.get("next_action") or st_name
        else:
            next_action = task_description or "Continue the current phase."

        parts.append(f"Focus now: {next_action}")

        decisions = last_decisions or list(state.get("recent_decisions", []))[-3:]
        decisions = list(reversed(decisions[-3:]))
        if decisions:
            parts.append("")
            parts.append("Recent decisions (last session):")
            for d in decisions:
                if isinstance(d, dict):
                    parts.append(f"  • {self.summarize_decision(d)}")

        files = last_files or state.get("files_being_modified", [])
        if files:
            parts.append("")
            parts.append("Files modified last session:")
            for f in files[:20]:
                parts.append(f"  • {f}")

        critical_avoid = [a for a in avoid_items if a.get("priority") == "critical"][:5]
        if not critical_avoid:
            critical_avoid = avoid_items[:3]
        if critical_avoid:
            parts.append("")
            parts.append("Critical avoid (do not repeat):")
            for item in critical_avoid:
                parts.append(f"  • {item.get('description', item)}")

        return parts

    def _build_tier2(
        self,
        state: dict[str, Any],
        tactical_ctx: dict[str, Any],
        file_paths: list[str],
        arch_nodes: list[dict[str, Any]],
        session_summary: str | None,
        root: Path,
    ) -> list[str]:
        parts: list[str] = []
        if state.get("description"):
            parts.append(f"Phase objectives: {state['description']}")

        subs = state.get("all_sub_tasks") or tactical_ctx.get("sub_tasks", [])
        if subs:
            parts.append("")
            parts.append("Sub-tasks in this phase:")
            for st in subs:
                if isinstance(st, dict):
                    mark = {"done": "✓", "in_progress": "→", "pending": "○", "blocked": "!"}.get(
                        st.get("status", ""), "?"
                    )
                    parts.append(
                        f"  {mark} {st.get('id')}: {st.get('name')} "
                        f"[{st.get('status')}, {st.get('progress', 0)}%]"
                    )

        paths = file_paths or [
            e["path"] for e in self.tactical.get_relevant_files(tactical_ctx.get("active_sub_task_id"))
        ]
        if paths:
            parts.append("")
            parts.append("Relevant files:")
            for p in paths[:12]:
                parts.append(f"  • {self.summarize_file(root / p if not Path(p).is_absolute() else p)}")

        if arch_nodes:
            parts.append("")
            parts.append("Architecture context:")
            for node in arch_nodes[:5]:
                deps = ", ".join(node.get("dependencies", [])[:5]) or "none"
                parts.append(
                    f"  • {node.get('id')}: {node.get('description', node.get('type', ''))} "
                    f"(depends on: {deps})"
                )

        if session_summary:
            parts.append("")
            parts.append(f"Recent sessions: {session_summary}")

        gotchas = tactical_ctx.get("gotchas", [])
        if gotchas:
            parts.append("")
            parts.append("Phase gotchas:")
            for g in gotchas[:5]:
                parts.append(f"  • {g}")

        return parts

    def _build_tier3(self) -> list[str]:
        summary = self.strategic.get_project_summary()
        parts = [
            f"Overall progress: {summary.get('overall_completion_percentage', 0)}% "
            f"({summary.get('completed_phases_count', 0)}/"
            f"{summary.get('total_phases', 0)} phases)",
        ]
        history = self.strategic.get_phase_history()
        if history:
            parts.append("Completed phases:")
            for h in history[-5:]:
                parts.append(f"  • {h.get('phase_id')}: {h.get('name')}")

        eff = self.tactical.get_phase_efficiency()
        if eff:
            parts.append(
                f"Phase efficiency: token ratio {eff.get('token_ratio')}, "
                f"{eff.get('subtasks_completed')}/{eff.get('subtasks_total')} sub-tasks done"
            )
        return parts

    def _fit_tier2(self, parts: list[str], budget: int) -> str:
        if budget <= 0 or not parts:
            return ""
        full = self._join_section("TIER 2 — PHASE CONTEXT", parts)
        if estimate_tokens(full) <= budget:
            return full
        essential = parts[: min(4, len(parts))]
        compressed = self._join_section("TIER 2 — PHASE CONTEXT (essential)", essential)
        if estimate_tokens(compressed) <= budget:
            return compressed
        one_line = " | ".join(re.sub(r"\s+", " ", p) for p in essential)[:500]
        return self._join_section("TIER 2 — PHASE CONTEXT (compressed)", [one_line])

    @staticmethod
    def _join_section(title: str, parts: list[str]) -> str:
        lines = [SECTION_MINOR, title, SECTION_MINOR, ""]
        lines.extend(parts)
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _resolve_active_subtask(
        state: dict[str, Any],
        tactical_ctx: dict[str, Any],
    ) -> dict[str, Any] | None:
        active_id = tactical_ctx.get("active_sub_task_id")
        subs = state.get("all_sub_tasks") or tactical_ctx.get("sub_tasks", [])
        for st in subs:
            if not isinstance(st, dict):
                continue
            if active_id and st.get("id") == active_id:
                return st
            if st.get("status") == "in_progress":
                return st
        active_list = state.get("active_sub_tasks", [])
        return active_list[0] if active_list else None
