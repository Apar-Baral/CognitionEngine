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


def git_author_from_config(config: Any) -> tuple[str, str] | None:
    """Author for auto-commits (your identity, not CE)."""
    import os

    name = (
        config.get("git.user_name")
        or config.get("git.author_name")
        or os.environ.get("CE_GIT_USER_NAME", "").strip()
    )
    email = (
        config.get("git.user_email")
        or config.get("git.author_email")
        or os.environ.get("CE_GIT_USER_EMAIL", "").strip()
    )
    if name and email:
        return str(name), str(email)
    return None


def _git_config_args(author: tuple[str, str] | None) -> list[str]:
    if not author:
        return []
    name, email = author
    return ["-c", f"user.name={name}", "-c", f"user.email={email}"]


def auto_commit(
    root: Path,
    summary: str,
    *,
    prefix: str = "ce:",
    paths: list[str] | None = None,
    respect_gitignore: bool = True,
    author: tuple[str, str] | None = None,
) -> str | None:
    """Stage and commit if repo is clean enough. Returns status message or None."""
    if not is_git_repo(root):
        return None
    root = root.resolve()
    message = f"{prefix} {summary}".strip()[:500]
    git_cmd = ["git", *_git_config_args(author)]
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
            [*git_cmd, "commit", "-m", message],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        who = f" as {author[0]} <{author[1]}>" if author else ""
        return f"Git: committed{who} — {message[:72]}"
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        if author is None and "user.name" in err.lower():
            return (
                "Git: commit skipped — set git.user_name and git.user_email in "
                "~/.cognition/config.yaml (see profile.example.yaml)"
            )
        return f"Git: commit skipped ({err[:120]})"


def should_auto_commit(config: Any) -> bool:
    return bool(config.get("git.auto_commit", False))


def auto_commit_prefix(config: Any) -> str:
    return str(config.get("git.auto_commit_message_prefix", "ce:") or "ce:")


def has_gh_cli() -> bool:
    try:
        r = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            check=False,
        )
        return r.returncode == 0
    except FileNotFoundError:
        return False


def get_git_remote_url(root: Path) -> str | None:
    if not is_git_repo(root):
        return None
    try:
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return r.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def push_to_github(
    root: Path,
    *,
    repo_name: str | None = None,
    private: bool = True,
    remote_url: str | None = None,
) -> tuple[bool, str]:
    """
    Push project to GitHub via `gh repo create` or manual remote.
    Returns (success, message).
    """
    root = root.resolve()
    if not is_git_repo(root):
        return False, "Not a git repository — run git init first."

    branch = "main"
    try:
        r = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        if r.stdout.strip():
            branch = r.stdout.strip()
    except subprocess.CalledProcessError:
        pass

    if has_gh_cli() and not remote_url:
        name = repo_name or root.name
        vis = "private" if private else "public"
        try:
            subprocess.run(
                [
                    "gh",
                    "repo",
                    "create",
                    name,
                    f"--{vis}",
                    "--source=.",
                    "--remote=origin",
                    "--push",
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            url = get_git_remote_url(root) or f"https://github.com/{name}"
            return True, f"Pushed to GitHub: {url}"
        except subprocess.CalledProcessError as exc:
            err = (exc.stderr or exc.stdout or str(exc)).strip()
            if "already exists" in err.lower() or "remote origin already exists" in err.lower():
                pass
            else:
                return False, f"gh repo create failed: {err[:200]}"

    if remote_url:
        subprocess.run(["git", "remote", "remove", "origin"], cwd=root, check=False, capture_output=True)
        subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )

    if not get_git_remote_url(root):
        return False, "No origin remote. Install GitHub CLI (`gh`) or provide a remote URL."

    try:
        subprocess.run(
            ["git", "push", "-u", "origin", branch],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        return True, f"Pushed to origin/{branch}: {get_git_remote_url(root)}"
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or exc.stdout or str(exc)).strip()
        return False, f"git push failed: {err[:200]}"


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
