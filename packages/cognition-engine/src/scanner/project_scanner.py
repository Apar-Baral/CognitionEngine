"""Scan project directory for language and file inventory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.constants import IGNORED_DIRECTORIES, SUPPORTED_EXTENSIONS


def detect_language(root: Path) -> str:
    counts: dict[str, int] = {}
    for path in root.rglob("*"):
        if not path.is_file() or any(p in IGNORED_DIRECTORIES for p in path.parts):
            continue
        lang = SUPPORTED_EXTENSIONS.get(path.suffix.lower())
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return "unknown"
    return max(counts, key=counts.get)


def scan_project(root: Path) -> dict[str, Any]:
    files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if len(files) < 2000:
            files.append(rel)
    lang = detect_language(root)
    framework = _guess_framework(root, lang)
    return {
        "root": str(root.resolve()),
        "language": lang,
        "framework": framework,
        "file_count": len(files),
        "sample_files": files[:30],
    }


def _guess_framework(root: Path, language: str) -> str:
    if (root / "pyproject.toml").is_file():
        text = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace")
        if "fastapi" in text.lower():
            return "fastapi"
        if "django" in text.lower():
            return "django"
        if "flask" in text.lower():
            return "flask"
    if (root / "package.json").is_file():
        return "node"
    return language
