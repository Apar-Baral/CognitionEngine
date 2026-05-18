"""Minimal agent tools with guardrails."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
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


def command_is_allowed(cmd_line: str) -> tuple[bool, str]:
    """Validate shell one-liner: each pipeline segment must start with an allowed command."""
    line = cmd_line.strip()
    if not line:
        return False, "empty command"
    lower = line.lower()
    for pat in _BLOCKED_PATTERNS:
        if re.search(pat, lower):
            return False, "blocked for safety"
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
        if base not in ALLOWED_COMMANDS:
            return False, f"'{base}' not in allowlist"
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
            for child in sorted(path.iterdir())[:200]:
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
        if len(text) > 12000:
            return text[:12000] + "\n…(truncated)"
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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Wrote {rel_path} ({len(content)} bytes)"

    def run_command(self, cmd_line: str) -> str:
        ok, reason = command_is_allowed(cmd_line)
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
            return out[:8000] or f"(exit {proc.returncode})"
        except subprocess.TimeoutExpired:
            return "Error: command timed out (180s)"
        except Exception as exc:
            return f"Error: {exc}"

    def suggest_next(self, ctx: object) -> str:
        try:
            from src.navigator.recommendation_engine import RecommendationEngine
            from src.navigator.complexity_forecaster import ComplexityForecaster
            from src.navigator.debt_detector import DebtDetector
            from src.navigator.dependency_resolver import DependencyResolver
            from src.navigator.phase_tracker import PhaseTracker

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
