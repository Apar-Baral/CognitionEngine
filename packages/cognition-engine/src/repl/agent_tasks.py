"""Claude Code–style task list derived from live agent activity."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.repl.markup_safe import escape_markup


@dataclass
class AgentTask:
    label: str
    status: str = "pending"  # pending | running | done | error


@dataclass
class TaskBoard:
    tasks: list[AgentTask] = field(default_factory=list)

    def upsert(self, label: str, status: str) -> None:
        label = label.strip()
        if not label:
            return
        for t in self.tasks:
            if t.label == label:
                t.status = status
                return
        self.tasks.append(AgentTask(label=label, status=status))

    def mark_running(self, label: str) -> None:
        self.upsert(label, "running")

    def mark_done(self, label: str) -> None:
        self.upsert(label, "done")

    def mark_error(self, label: str) -> None:
        self.upsert(label, "error")


_ICONS = {
    "pending": ("○", "#768390"),
    "running": ("◐", "#6cb6ff"),
    "done": ("✓", "#3fb950"),
    "error": ("✗", "#f85149"),
}


def ingest_activity(board: TaskBoard, msg: str) -> None:
    """Update task board from a single activity line."""
    m = msg.strip()
    lower = m.lower()
    if "▸ next action:" in lower:
        plan = m.split(":", 1)[-1].strip()
        board.mark_running(plan)
        return
    if lower.startswith("✓ done:") or lower.startswith("✓ done"):
        board.mark_done(board.tasks[-1].label if board.tasks else "Step")
        return
    if "writing file:" in lower or "✏️" in m:
        path = _after_colon(m)
        board.mark_running(f"Write {path}")
        return
    if "write result:" in lower or "wrote " in lower:
        if board.tasks:
            board.mark_done(board.tasks[-1].label)
        return
    if "reading file:" in lower or "📖" in m:
        board.mark_running(f"Read {_after_colon(m)}")
        return
    if "listing directory:" in lower or "📂" in m:
        board.mark_running(f"List {_after_colon(m)}")
        return
    if "deleting file:" in lower or "🗑" in m:
        board.mark_running(f"Delete {_after_colon(m)}")
        return
    if "deleted " in lower:
        if board.tasks:
            board.mark_done(board.tasks[-1].label)
        return
    if "running command:" in lower or "⚡ running" in lower:
        board.mark_running(f"Run {_after_colon(m)[:60]}")
        return
    if "command output:" in lower:
        if board.tasks:
            board.mark_done(board.tasks[-1].label)
        return
    if "permission required" in lower:
        board.mark_running("Awaiting your approval")
        return
    if "permission denied" in lower:
        board.mark_error("Permission denied")
        return
    if "permission granted" in lower:
        board.mark_done("Awaiting your approval")
        return
    if "model step" in lower:
        sm = re.search(r"step\s+(\d+)\s*/\s*(\d+)", lower)
        if sm:
            board.upsert(f"Model turn {sm.group(1)}/{sm.group(2)}", "running")
        return
    if "streaming model" in lower:
        board.upsert("Model thinking", "running")
        return
    if "response received" in lower:
        board.mark_done("Model thinking")
        if board.tasks and board.tasks[-1].label.startswith("Model turn"):
            board.mark_done(board.tasks[-1].label)
        return
    if "agent finished" in lower:
        board.upsert("Complete", "done")


def _after_colon(msg: str) -> str:
    if ":" in msg:
        return msg.split(":", 1)[-1].strip()
    return msg.strip()


def task_board_markup(board: TaskBoard, *, title: str = "Running") -> str:
    if not board.tasks:
        return f"[dim]{escape_markup(title)}…[/]"
    lines = [f"[bold #6cb6ff]{escape_markup(title)}[/]"]
    for t in board.tasks[-16:]:
        icon, color = _ICONS.get(t.status, _ICONS["pending"])
        lines.append(
            f"\n  [{color}]{icon}[/] [{color}]{escape_markup(t.label)}[/]"
        )
    return "".join(lines)
