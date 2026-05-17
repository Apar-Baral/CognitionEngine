"""Minimal valid DNA fixtures for tests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from src.core.constants import PhaseStatus, SessionType, TaskStatus
from src.dna.schema import DNA_SCHEMA_VERSION


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def minimal_valid_dna() -> dict[str, Any]:
    """Smallest DNA that passes schema + semantic validation."""
    return {
        "schema_version": DNA_SCHEMA_VERSION,
        "project": {
            "name": "test-project",
            "version": "0.1.0",
            "created": "2026-01-01",
            "last_updated": _now(),
            "total_sessions": 0,
            "total_tokens_consumed": 0,
            "total_hallucinations_caught": 0,
            "total_tokens_saved": 0,
        },
        "master_plan": {
            "total_phases": 2,
            "current_phase": 1,
            "phase_sequence": [
                _phase(
                    1,
                    PhaseStatus.IN_PROGRESS.value,
                    [
                        _subtask(1, 1, TaskStatus.IN_PROGRESS.value, 50),
                        _subtask(1, 2, TaskStatus.PENDING.value, 0),
                    ],
                ),
                _phase(2, PhaseStatus.NOT_STARTED.value, [_subtask(2, 1, TaskStatus.PENDING.value, 0)]),
            ],
        },
        "architecture_graph": {"nodes": [], "edges": []},
        "feature_registry": {
            "planned_features": [],
            "emergent_features": [],
            "integration_queue": [],
        },
        "deviation_history": [],
        "avoid_registry": {
            "hallucinations": [],
            "understood_files": [],
            "failed_approaches": [],
            "deprecated_patterns": [],
        },
        "insights": [],
        "recommendations": [],
        "rl_state": {
            "q_table": {},
            "learning_rate": 0.1,
            "exploration_rate": 0.1,
            "total_sessions_trained": 0,
        },
        "sessions_index": [],
    }


def invalid_phase_id_dna() -> dict[str, Any]:
    dna = minimal_valid_dna()
    dna["master_plan"]["phase_sequence"][1]["id"] = "PHASE_05"
    return dna


def _phase(num: int, status: str, sub_tasks: list[dict[str, Any]]) -> dict[str, Any]:
    pid = f"PHASE_{num:02d}"
    return {
        "id": pid,
        "name": f"Phase {num}",
        "description": f"Description {num}",
        "status": status,
        "completion_score": 0,
        "sessions_used": 0,
        "tokens_consumed": 0,
        "estimated_tokens": 10000,
        "budget_tokens": 12000,
        "deliverables": [],
        "dependencies": [f"PHASE_{num - 1:02d}"] if num > 1 else [],
        "blocked_by": [],
        "sub_tasks": sub_tasks,
        "state_history": [],
        "phase_type": SessionType.BUILD.value,
        "insights_generated": [],
    }


def _subtask(phase_num: int, task_num: int, status: str, progress: int) -> dict[str, Any]:
    return {
        "id": f"P{phase_num}_T{task_num}",
        "name": f"Task {task_num}",
        "status": status,
        "progress": progress,
        "files_modified": [],
        "completion_criteria": "Done when tests pass",
    }
