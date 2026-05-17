from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BootstrapPacket:
    """Host-agnostic session bootstrap output."""

    markdown: str
    metadata: dict[str, Any] = field(default_factory=dict)
    estimated_tokens: int = 0

    def write_files(self, cognition_dir: Any) -> None:
        from pathlib import Path

        base = Path(cognition_dir)
        base.mkdir(parents=True, exist_ok=True)
        (base / "bootstrap.md").write_text(self.markdown, encoding="utf-8")
        import json

        (base / "bootstrap_meta.json").write_text(
            json.dumps(self.metadata, indent=2),
            encoding="utf-8",
        )
