"""Git helpers for project setup and optional auto-commit on session end."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from src.core.constants import COGNITION_DIR


def bundled_gitignore_template() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "templates" / "project.gitignore"
        if candidate.is_file():
            return candidate
    return Path(__file__).resolve().parents[2] / "templates" / "project.gitignore"


def is_git_repo(root: Path) -> bool:
    return (root / ".git").is_dir()


def write_project_gitignore(root: Path, *, merge: bool = True) -> Path:
    """Write or merge CE gitignore template into project root."""
    template = bundled_gitignore_template()
    target = root / ".gitignore"
    block = template.read_text(encoding="utf-8") if template.is_file() else _default_gitignore()
    marker = "# Cognition Engine — runtime"
    if target.is_file() and merge:
        existing = target.read_text(encoding="utf-8")
        if marker in existing:
            return target
        target.write_text(existing.rstrip() + "\n\n" + block, encoding="utf-8")
    else:
        target.write_text(block, encoding="utf-8")
    return target


def git_init_project(
    root: Path,
    *,
    initial_commit: bool = True,
    commit_message: str = "chore: initialize project with Cognition Engine",
) -> list[str]:
    """Initialize git, apply gitignore, optional first commit of safe files only."""
    root = root.resolve()
    messages: list[str] = []
    write_project_gitignore(root)
    if not is_git_repo(root):
        subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True, text=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=root, check=False, capture_output=True)
        messages.append("Initialized git repository.")
    if initial_commit:
        msg = auto_commit(
            root,
            commit_message,
            paths=None,
            respect_gitignore=True,
        )
        if msg:
            messages.append(msg)
    return messages


def auto_commit(
    root: Path,
    summary: str,
    *,
    prefix: str = "ce:",
    paths: list[str] | None = None,
    respect_gitignore: bool = True,
) -> str | None:
    """Stage and commit if repo is clean enough. Returns status message or None."""
    if not is_git_repo(root):
        return None
    root = root.resolve()
    message = f"{prefix} {summary}".strip()[:500]
    try:
        if paths:
            for p in paths:
                subprocess.run(["git", "add", p], cwd=root, check=False, capture_output=True)
        else:
            subprocess.run(["git", "add", "-A"], cwd=root, check=False, capture_output=True)
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        if not status.stdout.strip():
            return "Git: nothing to commit."
        subprocess.run(
            ["git", "commit", "-m", message],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return f"Git: committed — {message[:80]}"
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        return f"Git: commit skipped ({err[:120]})"


def should_auto_commit(config: Any) -> bool:
    return bool(config.get("git.auto_commit", False))


def auto_commit_prefix(config: Any) -> str:
    return str(config.get("git.auto_commit_message_prefix", "ce:") or "ce:")


def _default_gitignore() -> str:
    return """# Cognition Engine runtime
.cognition/sessions/
.cognition/backups/
.cognition/metrics.db
.cognition/chroma/
.cognition/truth_chroma/
.cognition/memory_chroma/
.cognition/active_session.json
data/
.venv/
__pycache__/
*.pyc
.env
"""
