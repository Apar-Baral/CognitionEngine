"""
Predictive pre-compilation of session bootstrap context.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.bootstrap.bootstrap_generator import BootstrapGenerator
from src.bootstrap.context_compiler import estimate_tokens
from src.core.constants import COGNITION_DIR, TaskStatus
from src.core.types import BootstrapContext
from src.dna.query import DNAQuery
from src.memory.metrics_store import MetricsStore

CACHE_TTL_HOURS = 24
ACCURACY_REPORT_AFTER = 20


class Precompiler:
    """Anticipate next session and cache bootstrap context."""

    def __init__(
        self,
        generator: BootstrapGenerator,
        query: DNAQuery,
        metrics: MetricsStore,
        project_root: Path | str | None = None,
    ) -> None:
        self.generator = generator
        self.query = query
        self.metrics = metrics
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.cache_path = self.project_root / COGNITION_DIR / "precompile_cache.json"

    def predict_next_session(self) -> list[dict[str, Any]]:
        """Return ranked scenarios with probability and description."""
        state = self.generator.strategic.get_current_state()
        phase_id = state.get("phase_id") or ""
        phase = self.query.get_phase_by_id(phase_id) if phase_id else None
        scenarios: list[dict[str, Any]] = []

        active = _find_active_sub(state)
        progress = active.get("progress", 0) if active else 0
        blockers = state.get("blockers", []) if state.get("active") else []

        if blockers:
            scenarios.append(
                {
                    "scenario_id": "address_blocker",
                    "probability": 0.40,
                    "description": f"Address blocker(s): {'; '.join(blockers[:2])}",
                }
            )
            cont_prob = 0.35
            next_prob = 0.15
        else:
            cont_prob = 0.65 if progress < 85 else 0.25
            next_prob = 0.25 if progress >= 70 else 0.15

        if active:
            scenarios.append(
                {
                    "scenario_id": "continue_subtask",
                    "probability": cont_prob,
                    "description": (
                        f"Continue {active.get('id')}: {active.get('name')} "
                        f"({progress}% done)"
                    ),
                }
            )

        nxt = self._next_pending_subtask(phase) if phase else None
        if nxt:
            scenarios.append(
                {
                    "scenario_id": "next_subtask",
                    "probability": next_prob,
                    "description": f"Start next sub-task {nxt.get('id')}: {nxt.get('name')}",
                }
            )

        nxt_phase = self.query.get_next_executable_phase()
        if nxt_phase and phase and nxt_phase.get("id") != phase.get("id"):
            scenarios.append(
                {
                    "scenario_id": "next_phase",
                    "probability": 0.03,
                    "description": f"Start phase {nxt_phase.get('id')}: {nxt_phase.get('name')}",
                }
            )

        if not scenarios:
            scenarios.append(
                {
                    "scenario_id": "explore",
                    "probability": 1.0,
                    "description": "Review project plan and begin next executable work",
                }
            )

        total = sum(s["probability"] for s in scenarios)
        for s in scenarios:
            s["probability"] = round(s["probability"] / total, 3)
        scenarios.sort(key=lambda x: -x["probability"])
        return scenarios

    def precompile(self, scenario: dict[str, Any] | None = None) -> BootstrapContext:
        """Pre-generate bootstrap for the top (or given) scenario."""
        if scenario is None:
            scenarios = self.predict_next_session()
            scenario = scenarios[0] if scenarios else {"description": "Continue current work"}

        task = scenario.get("description", "Continue current work")
        ctx = self.generator.preview_bootstrap(task)
        self._write_cache(scenario.get("scenario_id", "default"), ctx, task)
        return ctx

    def warm_up(self) -> BootstrapContext | None:
        """Pre-compile the most likely bootstrap (e.g. on project open)."""
        self.invalidate_stale_caches()
        scenarios = self.predict_next_session()
        if not scenarios:
            return None
        return self.precompile(scenarios[0])

    def get_cached_bootstrap(self, scenario_id: str) -> BootstrapContext | None:
        """Return cached bootstrap if valid."""
        cache = self._load_cache()
        for entry in cache.get("entries", []):
            if entry.get("scenario_id") != scenario_id:
                continue
            created = entry.get("created_at", "")
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                continue
            if datetime.now(timezone.utc) - dt > timedelta(hours=CACHE_TTL_HOURS):
                continue
            if self._files_changed_since(entry.get("file_snapshot", {})):
                continue
            return entry.get("bootstrap_context")

        return None

    def record_prediction_outcome(self, scenario_id: str, was_correct: bool) -> None:
        """Track whether pre-compile matched actual session start."""
        cache = self._load_cache()
        acc = cache.setdefault("accuracy", {"correct": 0, "total": 0})
        acc["total"] = int(acc.get("total", 0)) + 1
        if was_correct:
            acc["correct"] = int(acc.get("correct", 0)) + 1
        self._save_cache(cache)
        total = acc["total"]
        if total >= ACCURACY_REPORT_AFTER:
            pct = round(100.0 * acc["correct"] / total)
            self.metrics.record_metric(
                "precompiler_accuracy",
                pct,
                tags={"sessions": total},
            )

    def prediction_accuracy(self) -> dict[str, Any]:
        cache = self._load_cache()
        acc = cache.get("accuracy", {"correct": 0, "total": 0})
        total = int(acc.get("total", 0))
        correct = int(acc.get("correct", 0))
        pct = round(100.0 * correct / total, 1) if total else 0.0
        latest = self.metrics.get_latest("precompiler_accuracy")
        return {
            "correct": correct,
            "total": total,
            "accuracy_percent": pct,
            "reported_metric": latest,
            "message": (
                f"Pre-compiler accuracy: {pct}%." if total >= ACCURACY_REPORT_AFTER else None
            ),
        }

    def invalidate_stale_caches(self) -> None:
        """Drop expired entries and entries invalidated by file changes."""
        cache = self._load_cache()
        kept: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for entry in cache.get("entries", []):
            created = entry.get("created_at", "")
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                continue
            if now - dt > timedelta(hours=CACHE_TTL_HOURS):
                continue
            if self._files_changed_since(entry.get("file_snapshot", {})):
                continue
            kept.append(entry)
        cache["entries"] = kept
        self._save_cache(cache)

    def _write_cache(
        self,
        scenario_id: str,
        ctx: BootstrapContext,
        task: str,
    ) -> None:
        cache = self._load_cache()
        entries = [e for e in cache.get("entries", []) if e.get("scenario_id") != scenario_id]
        entries.append(
            {
                "scenario_id": scenario_id,
                "task": task,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "bootstrap_context": ctx,
                "context_text": ctx.get("context_text", ""),
                "file_snapshot": self._file_snapshot(),
            }
        )
        cache["entries"] = entries
        self._save_cache(cache)

    def _file_snapshot(self) -> dict[str, float]:
        snapshot: dict[str, float] = {}
        for path in self.project_root.rglob("*"):
            if not path.is_file():
                continue
            if COGNITION_DIR in path.parts or ".git" in path.parts:
                continue
            try:
                snapshot[str(path.relative_to(self.project_root))] = path.stat().st_mtime
            except OSError:
                continue
            if len(snapshot) > 500:
                break
        return snapshot

    def _files_changed_since(self, snapshot: dict[str, float]) -> bool:
        if not snapshot:
            return False
        current = self._file_snapshot()
        for path, mtime in snapshot.items():
            if path not in current:
                return True
            if abs(current[path] - mtime) > 0.001:
                return True
        return False

    def _load_cache(self) -> dict[str, Any]:
        if not self.cache_path.is_file():
            return {"entries": [], "accuracy": {"correct": 0, "total": 0}}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"entries": [], "accuracy": {"correct": 0, "total": 0}}

    def _save_cache(self, data: dict[str, Any]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _next_pending_subtask(phase: dict[str, Any]) -> dict[str, Any] | None:
        for st in phase.get("sub_tasks", []):
            if isinstance(st, dict) and st.get("status") == TaskStatus.PENDING.value:
                return st
        return None


def _find_active_sub(state: dict[str, Any]) -> dict[str, Any] | None:
    active_list = state.get("active_sub_tasks", [])
    if active_list:
        return active_list[0]
    for st in state.get("all_sub_tasks", []):
        if isinstance(st, dict) and st.get("status") == TaskStatus.IN_PROGRESS.value:
            return st
    return None
