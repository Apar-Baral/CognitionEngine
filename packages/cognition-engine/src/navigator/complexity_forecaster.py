"""
Codebase complexity analysis and trend projection.
"""

from __future__ import annotations

import ast
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from src.dna.query import DNAQuery
from src.memory.metrics_store import MetricsStore

ComplexityTrend = Literal["increasing", "stable", "decreasing"]


class ComplexityForecaster:
    """Predict complexity growth and identify hotspots."""

    def __init__(self, query: DNAQuery, project_path: Path | str) -> None:
        self.query = query
        self.project_path = Path(project_path)
        name = query.refresh().get("project", {}).get("name", self.project_path.name)
        self.metrics = MetricsStore(self.project_path, name)

    def analyze_current_complexity(self) -> dict[str, Any]:
        """Scan codebase for complexity metrics."""
        py_files = list(self._iter_python_files())
        if not py_files:
            return {"files": 0, "scores": {}, "thresholds": _THRESHOLDS}

        line_counts: list[int] = []
        func_lengths: list[int] = []
        complexities: list[int] = []
        import_counts: list[int] = []

        for path in py_files:
            try:
                src = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lines = src.splitlines()
            line_counts.append(len(lines))
            import_counts.append(len(re.findall(r"^(?:import|from)\s+", src, re.M)))
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    end = getattr(node, "end_lineno", node.lineno) or node.lineno
                    func_lengths.append(max(1, end - node.lineno))
                    complexities.append(_cyclomatic(node))

        avg_lines = sum(line_counts) / len(line_counts)
        max_lines = max(line_counts) if line_counts else 0
        avg_func = sum(func_lengths) / len(func_lengths) if func_lengths else 0
        max_cc = max(complexities) if complexities else 0
        avg_cc = sum(complexities) / len(complexities) if complexities else 0

        scores = {
            "file_count": len(py_files),
            "avg_file_lines": round(avg_lines, 1),
            "max_file_lines": max_lines,
            "avg_function_length": round(avg_func, 1),
            "max_cyclomatic": max_cc,
            "avg_cyclomatic": round(avg_cc, 2),
            "avg_imports_per_file": round(
                sum(import_counts) / len(import_counts) if import_counts else 0, 1
            ),
        }
        warnings = []
        if max_lines > _THRESHOLDS["max_file_lines"]:
            warnings.append(f"Largest file exceeds {_THRESHOLDS['max_file_lines']} lines")
        if max_cc > _THRESHOLDS["max_cyclomatic"]:
            warnings.append(f"Max cyclomatic complexity {max_cc} is high")

        return {"files": len(py_files), "scores": scores, "warnings": warnings, "thresholds": _THRESHOLDS}

    def project_complexity_trend(self) -> dict[str, Any]:
        """Compare current metrics to historical snapshots."""
        current = self.analyze_current_complexity()
        score = current["scores"].get("avg_cyclomatic", 0)
        self.metrics.record_metric("complexity_avg_cc", score)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=30)
        history = self.metrics.get_metric_history("complexity_avg_cc", start=start, end=end)
        if len(history) < 2:
            trend: ComplexityTrend = "stable"
        else:
            recent = history[-1][1]
            older = history[0][1]
            if recent > older * 1.1:
                trend = "increasing"
            elif recent < older * 0.9:
                trend = "decreasing"
            else:
                trend = "stable"
        projection = score * 1.15 if trend == "increasing" else score
        return {
            "trend": trend,
            "current_avg_cc": score,
            "projected_2_weeks": round(projection, 2),
            "projected_10_sessions": round(score + 0.5 * len(history), 2),
        }

    def identify_hotspots(self, limit: int = 10) -> list[dict[str, Any]]:
        """Most complex files/functions."""
        hotspots: list[dict[str, Any]] = []
        for path in self._iter_python_files():
            try:
                src = path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(src)
            except (OSError, SyntaxError):
                continue
            rel = str(path.relative_to(self.project_path))
            lines = len(src.splitlines())
            max_cc = 0
            worst_fn = ""
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    cc = _cyclomatic(node)
                    if cc > max_cc:
                        max_cc = cc
                        worst_fn = node.name
            score = lines * 0.3 + max_cc * 5
            hotspots.append(
                {
                    "file": rel,
                    "lines": lines,
                    "max_cyclomatic": max_cc,
                    "worst_function": worst_fn,
                    "score": round(score, 1),
                    "recommendation": "Consider splitting or refactoring" if score > 80 else "Monitor",
                }
            )
        return sorted(hotspots, key=lambda x: -x["score"])[:limit]

    def estimate_feature_impact(self, feature_description: str) -> dict[str, Any]:
        """Heuristic complexity impact for a planned feature."""
        words = len(feature_description.split())
        base = self.analyze_current_complexity()["scores"].get("avg_cyclomatic", 5)
        impact = min(10.0, base * 0.1 + words * 0.05)
        if impact > 7:
            rec = "refactor_first"
        elif impact > 4:
            rec = "simplify"
        else:
            rec = "proceed"
        return {"impact_score": round(impact, 2), "recommendation": rec}

    def recommend_refactoring(self, limit: int = 5) -> list[dict[str, Any]]:
        """Prioritized refactor targets."""
        hotspots = self.identify_hotspots(limit * 2)
        return [
            {
                **h,
                "effort_tokens": int(h["score"] * 200),
                "benefit": "Lower hallucination risk and faster edits",
            }
            for h in hotspots[:limit]
        ]

    def _iter_python_files(self) -> Any:
        skip = {".git", ".cognition", "venv", ".venv", "node_modules", "__pycache__"}
        for path in self.project_path.rglob("*.py"):
            if any(part in skip for part in path.parts):
                continue
            yield path


_THRESHOLDS = {"max_file_lines": 800, "max_cyclomatic": 15, "max_function_lines": 80}


def _cyclomatic(node: ast.AST) -> int:
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
    return complexity
