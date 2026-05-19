"""Minimal agent tools with guardrails."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from difflib import SequenceMatcher
from pathlib import Path

# Base executables allowed in pipelines (first token of each segment).
ALLOWED_COMMANDS = frozenset(
    {
        "awk",
        "bash",
        "cat",
        "cd",
        "curl",
        "cut",
        "echo",
        "find",
        "git",
        "grep",
        "head",
        "less",
        "ls",
        "make",
        "mkdir",
        "mv",
        "cp",
        "node",
        "npm",
        "npx",
        "pip",
        "pip3",
        "pwd",
        "python",
        "python3",
        "pytest",
        "rg",
        "sed",
        "sh",
        "sort",
        "tail",
        "tee",
        "touch",
        "uniq",
        "wc",
        "which",
        "xargs",
    }
)

_BLOCKED_PATTERNS = (
    r"rm\s+-rf",
    r"rm\s+--no-preserve-root",
    r">\s*/dev/",
    r"mkfs\.",
    r":\(\)\s*\{",
    r"dd\s+if=",
    r"chmod\s+777\s+/",
    r"wget\s+.*\|\s*sh",
    r"curl\s+.*\|\s*sh",
)


def command_is_allowed(cmd_line: str, *, grants: frozenset[str] | None = None) -> tuple[bool, str]:
    """Validate shell one-liner: each pipeline segment must start with an allowed command."""
    line = cmd_line.strip()
    if not line:
        return False, "empty command"
    lower = line.lower()
    for pat in _BLOCKED_PATTERNS:
        if re.search(pat, lower):
            return False, "blocked for safety"
    from src.agent.permissions import PERM_DELETE, permission_for_command

    perm, danger = permission_for_command(line)
    if perm == PERM_DELETE and danger.startswith("Blocked dangerous"):
        return False, danger
    segments = re.split(r"\s*(?:\||&&|\|\|)\s*", line)
    for segment in segments:
        seg = segment.strip()
        if not seg:
            continue
        try:
            parts = shlex.split(seg)
        except ValueError as exc:
            return False, f"bad quoting: {exc}"
        if not parts:
            continue
        base = parts[0]
        extra = frozenset({"rm", "unlink"}) if grants and PERM_DELETE in grants else frozenset()
        if base not in ALLOWED_COMMANDS and base not in extra:
            return (
                False,
                f"'{base}' not in allowlist (delete needs approval via delete_file tool)",
            )
    return True, ""


class ToolRunner:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def list_dir(self, rel_path: str = ".") -> str:
        path = (self.root / rel_path).resolve()
        if not str(path).startswith(str(self.root)):
            return "Error: path outside project"
        if not path.is_dir():
            return f"Error: not a directory {rel_path}"
        entries: list[str] = []
        try:
            for child in sorted(path.iterdir())[:80]:
                kind = "/" if child.is_dir() else ""
                entries.append(f"{child.name}{kind}")
        except OSError as exc:
            return f"Error: {exc}"
        if not entries:
            return f"(empty directory {rel_path})"
        return "\n".join(entries)

    def read_file(self, rel_path: str) -> str:
        path = (self.root / rel_path).resolve()
        if not str(path).startswith(str(self.root)):
            return "Error: path outside project"
        if not path.is_file():
            return f"Error: not found {rel_path}"
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > 6000:
            return text[:6000] + "\n...(truncated; ask for a targeted section if needed)"
        return text

    def write_file(self, rel_path: str, content: str, ctx: object | None = None) -> str:
        path = (self.root / rel_path).resolve()
        if not str(path).startswith(str(self.root)):
            return "Error: path outside project"
        if path.suffix == ".py" and ctx is not None:
            try:
                from src.shield.import_validator import ImportValidator
                from src.shield.static_analyzer import StaticAnalyzer
                from src.shield.truth_database import TruthDatabase

                tdb = TruthDatabase(self.root)
                analyzer = StaticAnalyzer(tdb, ImportValidator(tdb, self.root))
                result = analyzer.validate(content, str(path))
                if not result.passed:
                    return f"Shield blocked write: {[e.description for e in result.errors[:3]]}"
            except Exception:
                pass
        old_text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        added, removed = _line_delta(old_text, content)
        action = "Updated" if path.is_file() else "Created"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"{action} {rel_path} (+{added} -{removed}, {len(content)} bytes)"

    def delete_file(self, rel_path: str) -> str:
        path = (self.root / rel_path).resolve()
        if not str(path).startswith(str(self.root)):
            return "Error: path outside project"
        if not path.exists():
            return f"Error: not found {rel_path}"
        if path.is_dir():
            return f"Error: {rel_path} is a directory (use run_command only if allowed)"
        try:
            path.unlink()
        except OSError as exc:
            return f"Error: could not delete {rel_path}: {exc}"
        return f"Deleted {rel_path}"

    def run_command(self, cmd_line: str, *, grants: frozenset[str] | None = None) -> str:
        ok, reason = command_is_allowed(cmd_line, grants=grants)
        if not ok:
            allowed = ", ".join(sorted(ALLOWED_COMMANDS))
            return (
                f"Error: command not allowed ({reason}).\n"
                f"Pipelines OK (| &&). Examples: grep -r foo . | head\n"
                f"Allowed: {allowed}"
            )
        try:
            proc = subprocess.run(
                cmd_line,
                shell=True,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=180,
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            if proc.returncode != 0 and not out.strip():
                out = f"(exit {proc.returncode})"
            return out[:4000] or f"(exit {proc.returncode})"
        except subprocess.TimeoutExpired:
            return "Error: command timed out (180s)"
        except Exception as exc:
            return f"Error: {exc}"

    def suggest_next(self, ctx: object) -> str:
        try:
            from src.navigator.complexity_forecaster import ComplexityForecaster
            from src.navigator.debt_detector import DebtDetector
            from src.navigator.dependency_resolver import DependencyResolver
            from src.navigator.phase_tracker import PhaseTracker
            from src.navigator.recommendation_engine import RecommendationEngine

            c = ctx  # ProjectContext
            rec = RecommendationEngine(
                PhaseTracker(c.query, c.mutator),
                DependencyResolver(c.query),
                ComplexityForecaster(c.query, c.root),
                DebtDetector(c.query, c.root),
                c.query,
            )
            return rec.get_next_session_prompt()
        except Exception as exc:
            return f"Could not suggest: {exc}"


def _line_delta(old: str, new: str) -> tuple[int, int]:
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    added = 0
    removed = 0
    for tag, i1, i2, j1, j2 in SequenceMatcher(a=old_lines, b=new_lines).get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return added, removed
