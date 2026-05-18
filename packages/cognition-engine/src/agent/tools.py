"""Minimal agent tools with guardrails."""

from __future__ import annotations

import subprocess
from pathlib import Path

ALLOWED_COMMANDS = frozenset(
    {
        "pytest",
        "python",
        "python3",
        "git",
        "ls",
        "cat",
        "pwd",
    }
)


class ToolRunner:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

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
        parts = cmd_line.strip().split()
        if not parts or parts[0] not in ALLOWED_COMMANDS:
            return f"Error: command not allowed. Allowed: {', '.join(sorted(ALLOWED_COMMANDS))}"
        try:
            proc = subprocess.run(
                parts,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=120,
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            return out[:4000] or f"(exit {proc.returncode})"
        except subprocess.TimeoutExpired:
            return "Error: command timed out"
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
