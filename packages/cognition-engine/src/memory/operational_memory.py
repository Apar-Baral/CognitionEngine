"""
Per-session operational memory.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.core.constants import SessionType, TaskStatus, budget_zone_for_ratio
from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery


class OperationalMemory:
    """Captures everything during a single session."""

    def __init__(
        self,
        session_id: int,
        project_path: Path | str,
        session_type: str | SessionType = SessionType.BUILD,
        budget_tokens: int = 75_000,
    ) -> None:
        self.session_id = session_id
        self.project_path = Path(project_path)
        self.session_type = (
            session_type.value if isinstance(session_type, SessionType) else session_type
        )
        self.budget_tokens = budget_tokens
        self.started_at = datetime.now(timezone.utc)
        self._api_calls: list[dict[str, Any]] = []
        self._file_ops: list[dict[str, Any]] = []
        self._hallucinations: list[dict[str, Any]] = []
        self._decisions: list[dict[str, Any]] = []
        self._user_interactions: list[dict[str, Any]] = []
        self._agent_actions: list[dict[str, Any]] = []

    def _ts(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def log_api_call(
        self,
        model_id: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        purpose: str = "",
        latency_ms: float = 0,
        succeeded: bool = True,
        reasoning_tokens: int = 0,
    ) -> None:
        self._api_calls.append(
            {
                "timestamp": self._ts(),
                "model_id": model_id,
                "provider": provider,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "reasoning_tokens": reasoning_tokens,
                "purpose": purpose,
                "latency_ms": latency_ms,
                "succeeded": succeeded,
            }
        )

    def log_file_operation(
        self,
        file_path: str,
        operation: str,
        hash_before: str,
        hash_after: str,
        agent_id: str = "default",
    ) -> None:
        self._file_ops.append(
            {
                "timestamp": self._ts(),
                "file_path": file_path,
                "operation": operation,
                "hash_before": hash_before,
                "hash_after": hash_after,
                "agent_id": agent_id,
            }
        )

    def log_hallucination(
        self,
        category: str,
        file_path: str,
        proposed_code: str,
        corrected_code: str,
        stage: int,
        auto_corrected: bool = False,
    ) -> None:
        self._hallucinations.append(
            {
                "timestamp": self._ts(),
                "category": category,
                "file_path": file_path,
                "proposed_code": proposed_code,
                "corrected_code": corrected_code,
                "stage": stage,
                "auto_corrected": auto_corrected,
            }
        )

    def log_decision(
        self,
        description: str,
        rationale: str,
        alternatives: list[str] | None = None,
        actor: str = "user",
    ) -> None:
        self._decisions.append(
            {
                "timestamp": self._ts(),
                "description": description,
                "rationale": rationale,
                "alternatives": alternatives or [],
                "actor": actor,
            }
        )

    def log_user_interaction(
        self,
        prompt: str,
        response: str,
        context: str = "",
    ) -> None:
        self._user_interactions.append(
            {
                "timestamp": self._ts(),
                "prompt": prompt,
                "response": response,
                "context": context,
            }
        )

    def log_agent_action(
        self,
        agent_id: str,
        agent_type: str,
        action: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._agent_actions.append(
            {
                "timestamp": self._ts(),
                "agent_id": agent_id,
                "agent_type": agent_type,
                "action": action,
                "details": details or {},
            }
        )

    def _total_tokens(self) -> dict[str, int]:
        inp = sum(c["input_tokens"] for c in self._api_calls)
        out = sum(c["output_tokens"] for c in self._api_calls)
        reasoning = sum(c.get("reasoning_tokens", 0) for c in self._api_calls)
        return {
            "input": inp,
            "output": out,
            "reasoning": reasoning,
            "total": inp + out + reasoning,
        }

    def get_session_summary(self) -> dict[str, Any]:
        ended = datetime.now(timezone.utc)
        duration = (ended - self.started_at).total_seconds()
        tokens = self._total_tokens()
        files_modified = {
            op["file_path"]
            for op in self._file_ops
            if op.get("operation") == "write"
        }
        by_category: dict[str, int] = {}
        for h in self._hallucinations:
            cat = h.get("category", "unknown")
            by_category[cat] = by_category.get(cat, 0) + 1

        budget_pct = (
            100.0 * tokens["total"] / self.budget_tokens if self.budget_tokens else 0
        )
        efficiency = max(
            0.0,
            min(
                100.0,
                100.0 - len(self._hallucinations) * 5 - self.get_re_read_report()["total_wasted_tokens"] / 100,
            ),
        )

        return {
            "session_id": self.session_id,
            "session_type": self.session_type,
            "duration_seconds": duration,
            "tokens": tokens,
            "cost_incurred": round(tokens["total"] * 0.000003, 4),
            "files_modified": list(files_modified),
            "files_modified_count": len(files_modified),
            "hallucinations_caught": len(self._hallucinations),
            "hallucinations_by_category": by_category,
            "decisions_count": len(self._decisions),
            "user_interactions_count": len(self._user_interactions),
            "agent_utilization": self._agent_stats(),
            "efficiency_score": round(efficiency, 2),
            "budget_adherence_percentage": round(100.0 - max(0, budget_pct - 100), 2),
            "api_calls_count": len(self._api_calls),
        }

    def get_realtime_stats(self) -> dict[str, Any]:
        tokens = self._total_tokens()
        used = tokens["total"]
        ratio = used / self.budget_tokens if self.budget_tokens else 0
        zone = budget_zone_for_ratio(ratio)
        elapsed = (datetime.now(timezone.utc) - self.started_at).total_seconds()
        active_agents = len(
            {a["agent_id"] for a in self._agent_actions if a.get("action") == "spawned"}
        ) - len(
            {a["agent_id"] for a in self._agent_actions if a.get("action") in ("completed", "failed")}
        )
        return {
            "tokens_used": used,
            "budget_tokens": self.budget_tokens,
            "budget_percentage": round(ratio * 100, 2),
            "zone": zone.value,
            "elapsed_seconds": elapsed,
            "cost_so_far": round(used * 0.000003, 4),
            "files_modified_count": len(
                {o["file_path"] for o in self._file_ops if o.get("operation") == "write"}
            ),
            "hallucinations_caught": len(self._hallucinations),
            "active_agents_count": max(0, active_agents),
        }

    def get_re_read_report(self) -> dict[str, Any]:
        reads: dict[str, list[str]] = {}
        for op in self._file_ops:
            if op.get("operation") == "read":
                reads.setdefault(op["file_path"], []).append(op["timestamp"])

        offenders: list[dict[str, Any]] = []
        total_waste = 0
        for path, timestamps in reads.items():
            if len(timestamps) > 1:
                writes_between = any(
                    o.get("operation") == "write" and o.get("file_path") == path
                    for o in self._file_ops
                )
                if not writes_between:
                    waste = (len(timestamps) - 1) * 500
                    total_waste += waste
                    offenders.append(
                        {
                            "file_path": path,
                            "read_count": len(timestamps),
                            "wasted_tokens_estimate": waste,
                        }
                    )

        return {
            "offenders": offenders,
            "total_wasted_tokens": total_waste,
        }

    def flush_to_dna(
        self,
        mutator: DNAMutator,
        query: DNAQuery,
        phase_id: str,
        sub_task_id: str | None = None,
        efficiency_score: float | None = None,
    ) -> dict[str, Any]:
        summary = self.get_session_summary()
        ended = datetime.now(timezone.utc).isoformat()
        score = efficiency_score if efficiency_score is not None else summary["efficiency_score"]

        mutator.add_session_record(
            session_id=self.session_id,
            started_at=self.started_at.isoformat(),
            ended_at=ended,
            phase_id=phase_id,
            session_type=self.session_type,
            tokens_consumed=summary["tokens"]["total"],
            efficiency_score=score,
        )

        for h in self._hallucinations:
            mutator.add_hallucination(
                {
                    "category": h["category"],
                    "proposed": h["proposed_code"],
                    "correct": h["corrected_code"],
                    "file_path": h["file_path"],
                    "session_id": self.session_id,
                }
            )

        if sub_task_id:
            phase = query.get_phase_by_id(phase_id)
            if phase:
                for st in phase.get("sub_tasks", []):
                    if st.get("id") == sub_task_id:
                        progress = min(100, st.get("progress", 0) + 25)
                        mutator.update_subtask_progress(
                            phase_id,
                            sub_task_id,
                            progress,
                            TaskStatus.DONE if progress >= 100 else TaskStatus.IN_PROGRESS,
                        )
                        break

        return summary

    def _agent_stats(self) -> dict[str, Any]:
        spawned = sum(1 for a in self._agent_actions if a.get("action") == "spawned")
        completed = sum(1 for a in self._agent_actions if a.get("action") == "completed")
        failed = sum(1 for a in self._agent_actions if a.get("action") == "failed")
        return {
            "spawned": spawned,
            "completed": completed,
            "failed": failed,
            "success_rate": round(completed / spawned, 2) if spawned else 1.0,
        }
