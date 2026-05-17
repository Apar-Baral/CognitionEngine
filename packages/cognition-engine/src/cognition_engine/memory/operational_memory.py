from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cognition_engine.core.constants import STATE_FILENAME
from cognition_engine.core.paths import cognition_dir


class OperationalMemory:
    """Active session state (ephemeral until ce end)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.state_path = cognition_dir(root) / STATE_FILENAME

    def load(self) -> dict[str, Any] | None:
        if not self.state_path.is_file():
            return None
        return json.loads(self.state_path.read_text(encoding="utf-8"))

    def start(self, session_id: str, session_type: str, budget_tokens: int) -> dict[str, Any]:
        from datetime import datetime, timezone

        state = {
            "session_id": session_id,
            "session_type": session_type,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "budget_tokens": budget_tokens,
            "tokens_used": 0,
            "active": True,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return state

    def clear(self) -> None:
        if self.state_path.is_file():
            self.state_path.unlink()

    def is_active(self) -> bool:
        state = self.load()
        return bool(state and state.get("active"))
