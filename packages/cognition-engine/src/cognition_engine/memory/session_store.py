from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cognition_engine.core.paths import sessions_dir


class SessionStore:
    """Append-only JSONL session logs."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.dir = sessions_dir(root)
        self.dir.mkdir(parents=True, exist_ok=True)

    def _log_path(self, session_id: str) -> Path:
        return self.dir / f"{session_id}.jsonl"

    def append_event(self, session_id: str, event: dict[str, Any]) -> None:
        event = {**event, "ts": datetime.now(timezone.utc).isoformat()}
        path = self._log_path(session_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def log_start(self, session_id: str, phase_id: str | None, sub_task_id: str | None) -> None:
        self.append_event(
            session_id,
            {"type": "session_start", "phase_id": phase_id, "sub_task_id": sub_task_id},
        )

    def log_end(
        self,
        session_id: str,
        summary: str,
        tokens_used: int,
        files_modified: list[str],
    ) -> None:
        self.append_event(
            session_id,
            {
                "type": "session_end",
                "summary": summary,
                "tokens_used": tokens_used,
                "files_modified": files_modified,
            },
        )
