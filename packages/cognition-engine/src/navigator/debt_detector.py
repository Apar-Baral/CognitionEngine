"""
Technical debt scanning and payoff prioritization.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.dna.query import DNAQuery

_DEBT_PATTERNS: list[tuple[str, str, str]] = [
    (r"\bTODO\b", "todo", "medium"),
    (r"\bFIXME\b", "fixme", "high"),
    (r"\bHACK\b", "hack", "high"),
    (r"\bXXX\b", "xxx", "medium"),
    (r"\bWORKAROUND\b", "workaround", "medium"),
]

_COMMENTED_CODE = re.compile(r"^\s*#\s*(def |class |import )", re.M)


@dataclass
class DebtItem:
    file_path: str
    line_number: int
    debt_type: str
    description: str
    severity: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "type": self.debt_type,
            "description": self.description,
            "severity": self.severity,
        }


class DebtDetector:
    """Find and prioritize technical debt."""

    def __init__(self, query: DNAQuery, project_path: Path | str) -> None:
        self.query = query
        self.project_path = Path(project_path)

    def scan_for_debt(self) -> list[dict[str, Any]]:
        """Scan codebase for debt markers."""
        items: list[DebtItem] = []
        skip = {".git", ".cognition", "venv", ".venv", "node_modules", "__pycache__"}
        for path in self.project_path.rglob("*"):
            if not path.is_file() or path.suffix not in (".py", ".js", ".ts", ".tsx", ".md"):
                continue
            if any(part in skip for part in path.parts):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            rel = str(path.relative_to(self.project_path))
            for i, line in enumerate(lines, 1):
                for pattern, dtype, severity in _DEBT_PATTERNS:
                    if re.search(pattern, line, re.I):
                        items.append(
                            DebtItem(rel, i, dtype, line.strip()[:120], severity)
                        )
                if _COMMENTED_CODE.search(line):
                    items.append(
                        DebtItem(rel, i, "commented_code", "Commented-out code", "low")
                    )
            if path.suffix == ".py" and len(lines) > 800:
                items.append(
                    DebtItem(rel, 1, "large_file", f"File has {len(lines)} lines", "medium")
                )
        return [it.to_dict() for it in items]

    def track_debt_age(self) -> list[dict[str, Any]]:
        """Age debt items via git blame when available."""
        items = self.scan_for_debt()
        for item in items:
            item["age_days"] = self._git_age_days(item["file_path"], item["line_number"])
        return sorted(items, key=lambda x: -x.get("age_days", 0))

    def calculate_debt_interest(self) -> list[dict[str, Any]]:
        """Estimated token cost per session per debt item."""
        items = self.track_debt_age()
        severity_rate = {"high": 3000, "medium": 1500, "low": 500}
        for item in items:
            rate = severity_rate.get(item.get("severity", "low"), 500)
            age = item.get("age_days", 0)
            item["interest_per_session"] = rate
            item["cumulative_cost"] = rate * max(1, age // 7)
        return items

    def debt_accumulation_rate(self, days: int = 7) -> dict[str, Any]:
        """New vs resolved debt (from session history heuristic)."""
        items = self.scan_for_debt()
        by_type: dict[str, int] = {}
        for it in items:
            by_type[it["type"]] = by_type.get(it["type"], 0) + 1
        total = len(items)
        # Without historical debt DB, estimate from deviations
        deviations = self.query.refresh().get("deviation_history", [])
        recent = [d for d in deviations if isinstance(d, dict)][-days:]
        resolved = sum(1 for d in recent if d.get("resolved"))
        new = total // max(days, 1)
        net = new - resolved
        weeks_to_critical = max(1, (50 - total) // max(net, 1)) if net > 0 else 999
        return {
            "period_days": days,
            "new_estimated": new,
            "resolved": resolved,
            "net": net,
            "total_items": total,
            "by_type": by_type,
            "weeks_to_critical": weeks_to_critical,
        }

    def recommend_payoff_order(self, limit: int = 10) -> list[dict[str, Any]]:
        """Prioritize debt payoff by interest, age, and impact."""
        items = self.calculate_debt_interest()
        for item in items:
            score = item.get("interest_per_session", 0)
            score += item.get("age_days", 0) * 10
            if item.get("severity") == "high":
                score *= 1.5
            item["priority_score"] = score
            item["payoff_tokens"] = 15000 if item.get("severity") == "high" else 8000
            item["expected_savings_per_session"] = item.get("interest_per_session", 0) // 2
        return sorted(items, key=lambda x: -x["priority_score"])[:limit]

    def calculate_roi(self, debt_item: dict[str, Any], sessions_ahead: int = 20) -> dict[str, Any]:
        """ROI of fixing debt now vs later."""
        fix_cost = debt_item.get("payoff_tokens", 15000)
        savings = debt_item.get("interest_per_session", 1000) // 2
        cumulative = savings * sessions_ahead
        break_even = fix_cost / savings if savings else 999
        return {
            "fix_cost_tokens": fix_cost,
            "savings_per_session": savings,
            "sessions_ahead": sessions_ahead,
            "cumulative_savings": cumulative,
            "break_even_session": round(break_even, 1),
            "roi_positive": cumulative > fix_cost,
        }

    def _git_age_days(self, rel_path: str, line: int) -> int:
        full = self.project_path / rel_path
        if not full.is_file():
            return 0
        try:
            result = subprocess.run(
                ["git", "blame", "-L", f"{line},{line}", "--porcelain", str(full)],
                capture_output=True,
                text=True,
                cwd=self.project_path,
                timeout=5,
                check=False,
            )
            if result.returncode != 0:
                return 0
            for row in result.stdout.splitlines():
                if row.startswith("author-time "):
                    ts = int(row.split()[1])
                    then = datetime.fromtimestamp(ts, tz=timezone.utc)
                    return (datetime.now(timezone.utc) - then).days
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return 0
        return 0
