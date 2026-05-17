"""
Real-time session usage pattern analysis.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from src.memory.operational_memory import OperationalMemory


class UsageAnalyzer:
    """Detect re-reads, loops, runaway usage, and efficiency during a session."""

    RE_READ_THRESHOLD = 3

    def __init__(
        self,
        operational: OperationalMemory,
        file_operations: list[dict[str, Any]] | None = None,
    ) -> None:
        self.operational = operational
        self.file_operations = file_operations or operational.file_operations
        self._recent_responses: list[str] = []

    def detect_re_read(self) -> list[dict[str, Any]]:
        """Files read 3+ times with same content hash waste tokens."""
        hash_reads: dict[str, dict[str, Any]] = {}
        for op in self.file_operations:
            if op.get("operation") != "read":
                continue
            path = op.get("file_path", "")
            h = op.get("hash_after") or op.get("hash_before") or ""
            key = f"{path}:{h}"
            entry = hash_reads.setdefault(
                key,
                {"file_path": path, "content_hash": h, "read_count": 0, "wasted_tokens_estimate": 0},
            )
            entry["read_count"] += 1

        flagged: list[dict[str, Any]] = []
        for entry in hash_reads.values():
            if entry["read_count"] >= self.RE_READ_THRESHOLD:
                waste = (entry["read_count"] - 1) * 500
                entry["wasted_tokens_estimate"] = waste
                flagged.append(entry)
        return sorted(flagged, key=lambda x: -x["wasted_tokens_estimate"])

    def record_response(self, response_text: str) -> None:
        self._recent_responses.append(response_text[:2000])
        if len(self._recent_responses) > 10:
            self._recent_responses.pop(0)

    def detect_loop(self) -> dict[str, Any]:
        window = self._recent_responses[-10:]
        if len(window) < 4:
            return {"detected": False, "confidence": 0.0, "description": ""}

        normalized = [_normalize(t) for t in window]
        counts = Counter(normalized)
        most_common, freq = counts.most_common(1)[0]
        if freq >= 4:
            return {
                "detected": True,
                "confidence": min(1.0, freq / len(window)),
                "description": f"Similar response repeated {freq} times in last {len(window)} calls",
            }

        tool_sigs = [_tool_signature(t) for t in window]
        tool_counts = Counter(tool_sigs)
        t_common, t_freq = tool_counts.most_common(1)[0]
        if t_freq >= 4 and t_common:
            return {
                "detected": True,
                "confidence": 0.85,
                "description": f"Repeated tool pattern: {t_common}",
            }

        return {"detected": False, "confidence": 0.0, "description": ""}

    def detect_runaway(self) -> dict[str, Any]:
        calls = self.operational.api_calls
        if len(calls) < 3:
            return {"detected": False, "description": ""}

        totals = [c["input_tokens"] + c["output_tokens"] for c in calls]
        mean = sum(totals) / len(totals)
        variance = sum((x - mean) ** 2 for x in totals) / len(totals)
        std = variance**0.5

        recent = calls[-5:]
        recent_rate = sum(c["input_tokens"] + c["output_tokens"] for c in recent) / max(
            1, len(recent)
        )
        if std > 0 and recent_rate > mean + 3 * std:
            return {
                "detected": True,
                "description": (
                    f"Token rate spike: recent avg {recent_rate:.0f} vs session mean {mean:.0f}"
                ),
            }

        last = totals[-1] if totals else 0
        if std > 0 and last > mean + 3 * std:
            return {
                "detected": True,
                "description": f"Single call anomaly: {last} tokens (mean {mean:.0f})",
            }

        return {"detected": False, "description": ""}

    def calculate_efficiency_score(self) -> float:
        calls = self.operational.api_calls
        if not calls:
            return 100.0

        total_tokens = sum(c["input_tokens"] + c["output_tokens"] for c in calls)
        writes = [o for o in self.file_operations if o.get("operation") == "write"]
        lines_written = len(writes) * 20
        code_ratio = min(100.0, (lines_written / max(1, total_tokens)) * 1000)

        re_reads = self.detect_re_read()
        re_read_tokens = sum(r["wasted_tokens_estimate"] for r in re_reads)
        re_read_ratio = re_read_tokens / max(1, total_tokens)
        re_read_score = max(0.0, 100.0 - re_read_ratio * 200)

        reads = sum(1 for o in self.file_operations if o.get("operation") == "read")
        productive = sum(1 for c in calls if c.get("succeeded", True))
        tool_eff = (productive / max(1, len(calls))) * 100
        if reads > len(calls):
            tool_eff *= 0.7

        score = 0.4 * code_ratio + 0.3 * re_read_score + 0.2 * tool_eff + 0.1 * 80.0
        return round(min(100.0, max(0.0, score)), 2)

    def get_session_efficiency_report(self) -> dict[str, Any]:
        score = self.calculate_efficiency_score()
        recommendations: list[str] = []
        for item in self.detect_re_read():
            recommendations.append(
                f"You've re-read {item['file_path']} {item['read_count']} times. "
                "Add it to the understood files list to prevent this."
            )
        reads = sum(1 for o in self.file_operations if o.get("operation") == "read")
        calls = len(self.operational.api_calls)
        if calls and reads / calls > 0.45:
            recommendations.append(
                f"{reads / calls:.0%} of activity was file reads. "
                "Consider loading relevant files into context at session start."
            )
        loop = self.detect_loop()
        if loop.get("detected"):
            recommendations.append(f"Possible loop: {loop.get('description')}")

        return {
            "efficiency_score": score,
            "re_read_tax": self.get_re_read_tax(),
            "recommendations": recommendations,
            "loop_detection": loop,
            "runaway_detection": self.detect_runaway(),
        }

    def get_re_read_tax(self) -> dict[str, Any]:
        flagged = self.detect_re_read()
        tokens = sum(f["wasted_tokens_estimate"] for f in flagged)
        cost = round(tokens * 0.000003, 4)
        return {
            "wasted_tokens": tokens,
            "estimated_cost_usd": cost,
            "files": flagged,
        }


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())[:500]


def _tool_signature(text: str) -> str:
    if "tool" in text.lower() or "function" in text.lower():
        return hashlib.md5(text[:300].encode()).hexdigest()[:12]
    return ""
