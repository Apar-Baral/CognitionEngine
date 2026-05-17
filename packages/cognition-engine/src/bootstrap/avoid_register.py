"""
Avoid register — externalized memory of failures and known-good facts.
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.constants import HallucinationCategory
from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text) if len(t) > 2}


def _tags_from_path(file_context: str) -> list[str]:
    norm = file_context.replace("\\", "/")
    tags = [norm]
    parts = Path(norm).parts
    tags.extend(parts)
    if "." in Path(norm).name:
        tags.append(Path(norm).suffix.lstrip("."))
    return [t for t in tags if t]


class AvoidRegister:
    """Query and maintain the DNA avoid registry."""

    def __init__(self, query: DNAQuery, mutator: DNAMutator | None = None) -> None:
        self.query = query
        self.mutator = mutator

    def get_relevant_avoid_items(
        self,
        task_context: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return avoid items scored by keyword overlap with task_context."""
        context_tokens = _tokenize(task_context)
        reg = self.query._data().get("avoid_registry", {})
        candidates: list[dict[str, Any]] = []

        for item in reg.get("hallucinations", []):
            if isinstance(item, dict):
                candidates.append({**item, "_category": "hallucination"})

        for item in reg.get("failed_approaches", []):
            if isinstance(item, dict):
                candidates.append({**item, "_category": "failed_approach"})

        for path in reg.get("understood_files", []):
            candidates.append(
                {
                    "id": f"understood_{path}",
                    "type": "understood_file",
                    "description": f"The file {path} is fully understood. Do not re-read it.",
                    "relevance_tags": _tags_from_path(path),
                    "decay_count": 0,
                    "_category": "understood_file",
                }
            )

        for pattern in reg.get("deprecated_patterns", []):
            text = pattern if isinstance(pattern, str) else str(pattern)
            candidates.append(
                {
                    "id": f"deprecated_{hash(text) % 10_000}",
                    "type": "deprecated_pattern",
                    "description": text,
                    "relevance_tags": list(_tokenize(text)),
                    "decay_count": 0,
                    "_category": "deprecated_pattern",
                }
            )

        scored: list[tuple[float, dict[str, Any]]] = []
        for item in candidates:
            tags = set(item.get("relevance_tags", []))
            tags |= _tokenize(item.get("description", ""))
            tags |= _tokenize(item.get("context", "") or item.get("file_path", ""))
            matches = len(context_tokens & {t.lower() for t in tags})
            decay = item.get("decay_count", 0)
            score = matches * 10.0 - decay * 0.5
            if matches > 0 or decay == 0:
                scored.append((score, item))

        scored.sort(key=lambda x: -x[0])
        results = [item for _, item in scored[:limit]]
        self._touch_items(results)
        return results

    def add_hallucination(
        self,
        category: str | HallucinationCategory,
        proposed_code: str,
        corrected_code: str,
        explanation: str,
        file_context: str,
        session_id: int | None = None,
    ) -> dict[str, Any]:
        if not self.mutator:
            raise RuntimeError("DNAMutator required for add_hallucination")
        cat = category.value if isinstance(category, HallucinationCategory) else category
        tags = _tags_from_path(file_context)
        tags.append(cat)
        tags.extend(_tokenize(proposed_code))
        record = {
            "id": f"HALL_{uuid.uuid4().hex[:8].upper()}",
            "category": cat,
            "proposed_code": proposed_code,
            "corrected_code": corrected_code,
            "explanation": explanation,
            "file_path": file_context,
            "description": (
                f"Do not use `{proposed_code[:80]}` — {explanation}. "
                f"Use `{corrected_code[:80]}` instead."
            ),
            "relevance_tags": sorted(set(tags)),
            "decay_count": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.mutator.add_hallucination(record, session_id=session_id)
        self.query.refresh()
        return record

    def add_understood_file(self, path: str) -> None:
        if not self.mutator:
            raise RuntimeError("DNAMutator required for add_understood_file")
        self.mutator.add_understood_file(path)
        self.query.refresh()

    def add_failed_approach(
        self,
        approach: str,
        reason: str,
        relevance_tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if not self.mutator:
            raise RuntimeError("DNAMutator required for add_failed_approach")
        tags = list(relevance_tags or [])
        tags.extend(_tokenize(approach))
        record = {
            "id": f"FAIL_{uuid.uuid4().hex[:8].upper()}",
            "type": "failed_approach",
            "description": f"Failed approach: {approach}. Reason: {reason}",
            "approach": approach,
            "reason": reason,
            "relevance_tags": sorted(set(tags)),
            "decay_count": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.mutator.add_failed_approach(record)
        self.query.refresh()
        return record

    def is_file_understood(self, path: str) -> bool:
        norm = path.replace("\\", "/")
        understood = self.query._data().get("avoid_registry", {}).get("understood_files", [])
        return norm in understood or path in understood

    def get_hallucination_stats(self) -> dict[str, Any]:
        items = self.query._data().get("avoid_registry", {}).get("hallucinations", [])
        categories: Counter[str] = Counter()
        packages: Counter[str] = Counter()
        by_month: Counter[str] = Counter()

        for item in items:
            if not isinstance(item, dict):
                continue
            cat = item.get("category", "unknown")
            categories[cat] += 1
            proposed = item.get("proposed_code", "")
            for pkg in re.findall(r"['\"]([a-zA-Z0-9_.]+)['\"]", proposed):
                if "." in pkg or "_" in pkg:
                    packages[pkg.split(".")[0]] += 1
            ts = item.get("timestamp", "")[:7]
            if ts:
                by_month[ts] += 1

        months = sorted(by_month.keys())
        trend = "stable"
        if len(months) >= 2:
            if by_month[months[-1]] > by_month[months[-2]]:
                trend = "increasing"
            elif by_month[months[-1]] < by_month[months[-2]]:
                trend = "decreasing"

        return {
            "total": len(items),
            "top_categories": categories.most_common(5),
            "top_packages": packages.most_common(5),
            "trend": trend,
            "by_month": dict(by_month),
        }

    def decay_management(self, accessed_ids: set[str] | None = None) -> None:
        """Increment decay for unaccessed items; reset decay for accessed ones."""
        if not self.mutator:
            return
        self.mutator.manage_avoid_decay(accessed_ids or set())
        self.query.refresh()

    def _touch_items(self, items: list[dict[str, Any]]) -> None:
        ids = {item.get("id", "") for item in items if item.get("id")}
        if ids:
            self.decay_management(accessed_ids=ids)
