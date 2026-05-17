from __future__ import annotations

from pathlib import Path

LANGUAGE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
}


def detect_language(root: Path) -> str:
    counts: dict[str, int] = {}
    ignore = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cognition"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignore for part in path.parts):
            continue
        lang = LANGUAGE_EXTENSIONS.get(path.suffix.lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return "unknown"
    return max(counts, key=counts.get)
