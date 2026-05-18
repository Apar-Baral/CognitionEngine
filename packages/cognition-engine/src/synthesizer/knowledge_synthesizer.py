"""
Post-session knowledge synthesis and insight generation.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery
from src.memory.metrics_store import MetricsStore
from src.memory.session_store import SessionStore
from src.memory.session_tokens import session_tokens_consumed
from src.synthesizer.trend_analyzer import TrendAnalyzer


class KnowledgeSynthesizer:
    """Analyze sessions and produce actionable insights."""

    def __init__(
        self,
        query: DNAQuery,
        mutator: DNAMutator,
        session_store: SessionStore,
        metrics: MetricsStore,
    ) -> None:
        self.query = query
        self.mutator = mutator
        self.session_store = session_store
        self.metrics = metrics
        self.trends = TrendAnalyzer()

    def synthesize(self, session_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Run all pipelines and persist insights."""
        sessions = self._load_recent_sessions(20)
        sessions.append(session_data)
        analyses = [
            self._productivity_patterns(sessions),
            self._hallucination_trends(sessions),
            self._estimation_accuracy(sessions),
            self._optimal_conditions(sessions),
            self._debt_impact(sessions),
        ]
        insights = self.generate_insights(analyses, session_data)
        for ins in insights:
            self.mutator.add_insight(ins)
        return insights

    def generate_insights(
        self, analyses: list[list[dict[str, Any]]], session_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        sid = int(session_data.get("session_id", 0))
        records: list[dict[str, Any]] = []
        for group in analyses:
            for item in group:
                conf = float(item.get("confidence", 0.5))
                records.append(
                    {
                        "id": f"ins_{uuid.uuid4().hex[:10]}",
                        "type": item.get("type", "general"),
                        "finding": item["finding"],
                        "confidence": conf,
                        "generated_at": now,
                        "session_id": sid,
                        "actionability": item.get("actionability", "MEDIUM"),
                        "applied": False,
                        "impact_if_applied": item.get("impact", ""),
                    }
                )
        return records

    def apply_insight(self, insight_id: str) -> dict[str, Any] | None:
        def apply(dna: dict[str, Any]) -> None:
            for ins in dna.get("insights", []):
                if ins.get("id") == insight_id:
                    ins["applied"] = True
                    ins["applied_at"] = datetime.now(timezone.utc).isoformat()

        self.mutator._mutate("apply_insight", apply)
        for ins in self.query.refresh().get("insights", []):
            if ins.get("id") == insight_id:
                return ins
        return None

    def get_insights(
        self,
        *,
        insight_type: str | None = None,
        min_confidence: float = 0.0,
        actionability: str | None = None,
        applied_only: bool | None = None,
    ) -> list[dict[str, Any]]:
        items = self.query.refresh().get("insights", [])
        out = []
        for ins in items:
            if not isinstance(ins, dict):
                continue
            if insight_type and ins.get("type") != insight_type:
                continue
            if ins.get("confidence", 0) < min_confidence:
                continue
            if actionability and ins.get("actionability") != actionability:
                continue
            if applied_only is True and not ins.get("applied"):
                continue
            if applied_only is False and ins.get("applied"):
                continue
            out.append(ins)
        return out

    def _load_recent_sessions(self, n: int) -> list[dict[str, Any]]:
        if hasattr(self.session_store, "get_recent_sessions"):
            return self.session_store.get_recent_sessions(n)
        return self.query.refresh().get("sessions_index", [])[-n:]

    def _productivity_patterns(self, sessions: list[dict[str, Any]]) -> list[dict]:
        by_hour: dict[int, list[float]] = defaultdict(list)
        for s in sessions:
            started = s.get("started_at") or s.get("date", "")
            eff = float(s.get("efficiency_score", s.get("efficiency", 0)))
            if started and len(started) >= 13:
                try:
                    hour = int(started[11:13])
                    by_hour[hour].append(eff)
                except ValueError:
                    pass
        if len(by_hour) < 2:
            return []
        avgs = {h: sum(v) / len(v) for h, v in by_hour.items() if v}
        if not avgs:
            return []
        best_h = max(avgs, key=avgs.get)
        worst_h = min(avgs, key=avgs.get)
        if avgs[best_h] > avgs[worst_h] * 1.15:
            return [
                {
                    "type": "productivity",
                    "finding": (
                        f"Sessions around {best_h}:00 are "
                        f"{((avgs[best_h] / avgs[worst_h]) - 1) * 100:.0f}% more efficient "
                        f"than around {worst_h}:00."
                    ),
                    "confidence": 0.75,
                    "actionability": "MEDIUM",
                    "impact": "Schedule complex work in peak hours.",
                }
            ]
        return []

    def _hallucination_trends(self, sessions: list[dict[str, Any]]) -> list[dict]:
        rates = []
        categories: Counter[str] = Counter()
        for s in sessions[-10:]:
            caught = int(s.get("hallucinations_caught", 0))
            tokens = session_tokens_consumed(s) or 1000
            rates.append(caught / max(tokens, 1) * 1000)
            for h in s.get("hallucinations", []):
                if isinstance(h, dict):
                    categories[h.get("category", "unknown")] += 1
        if len(rates) < 3:
            return []
        trend = self.trends.calculate_trend(rates)
        findings = []
        if trend["direction"] == "increasing":
            top = categories.most_common(1)
            cat = top[0][0] if top else "unknown"
            findings.append(
                {
                    "type": "hallucination",
                    "finding": (
                        f"Hallucination rate is increasing over the last {len(rates)} sessions. "
                        f"Most common type: {cat}."
                    ),
                    "confidence": 0.8,
                    "actionability": "HIGH",
                    "impact": "Tighten shield sensitivity or reduce context size.",
                }
            )
        return findings

    def _estimation_accuracy(self, sessions: list[dict[str, Any]]) -> list[dict]:
        deltas = []
        for s in sessions[-10:]:
            pred = float(s.get("predicted_tokens", 0))
            actual = float(session_tokens_consumed(s))
            if pred > 0 and actual > 0:
                deltas.append((actual - pred) / pred)
        if len(deltas) < 5:
            return []
        avg = sum(deltas) / len(deltas)
        if abs(avg) > 0.1:
            direction = "below" if avg > 0 else "above"
            return [
                {
                    "type": "estimation",
                    "finding": (
                        f"Token estimates have been {abs(avg) * 100:.0f}% {direction} actual "
                        f"consumption over the last {len(deltas)} sessions."
                    ),
                    "confidence": 0.7,
                    "actionability": "HIGH",
                    "impact": "Adjust budget buffer in cc plan / start.",
                }
            ]
        return []

    def _optimal_conditions(self, sessions: list[dict[str, Any]]) -> list[dict]:
        single = [s for s in sessions if int(s.get("agent_count", 1)) <= 1]
        multi = [s for s in sessions if int(s.get("agent_count", 1)) > 1]
        if len(single) < 3 or len(multi) < 2:
            return []
        e_single = sum(float(s.get("efficiency_score", 50)) for s in single) / len(single)
        e_multi = sum(float(s.get("efficiency_score", 50)) for s in multi) / len(multi)
        if e_multi > e_single * 1.2:
            return [
                {
                    "type": "optimal_conditions",
                    "finding": (
                        f"Multi-agent sessions are "
                        f"{((e_multi / e_single) - 1) * 100:.0f}% more efficient than single-agent."
                    ),
                    "confidence": 0.65,
                    "actionability": "MEDIUM",
                }
            ]
        return []

    def _debt_impact(self, sessions: list[dict[str, Any]]) -> list[dict]:
        high_debt = [s for s in sessions if int(s.get("debt_items_touched", 0)) >= 5]
        clean = [s for s in sessions if int(s.get("debt_items_touched", 0)) < 2]
        if len(high_debt) < 2 or len(clean) < 2:
            return []
        t_high = sum(session_tokens_consumed(s) for s in high_debt) / len(high_debt)
        t_clean = sum(session_tokens_consumed(s) for s in clean) / len(clean)
        if t_high > t_clean * 1.2:
            return [
                {
                    "type": "technical_debt",
                    "finding": (
                        f"Sessions on high-debt files consume "
                        f"{((t_high / t_clean) - 1) * 100:.0f}% more tokens than clean files."
                    ),
                    "confidence": 0.7,
                    "actionability": "HIGH",
                    "impact": "Pay down TODO-heavy modules before large features.",
                }
            ]
        return []
