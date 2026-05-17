from __future__ import annotations

from pathlib import Path
from typing import Any

from cognition_engine.scanner.language_detector import detect_language


def scan_project(root: Path) -> dict[str, Any]:
    ignore = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cognition"}
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignore for part in path.parts):
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if len(files) < 500:
            files.append(rel)
    return {
        "root": str(root.resolve()),
        "language": detect_language(root),
        "file_count": len(files),
        "sample_files": files[:30],
    }
