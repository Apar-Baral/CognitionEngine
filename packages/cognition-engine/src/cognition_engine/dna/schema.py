from __future__ import annotations

from typing import Any

from cognition_engine.core.constants import PhaseStatus, SubTaskStatus
from cognition_engine.core.exceptions import DnaValidationError

SCHEMA_VERSION = 1


def empty_dna(project_name: str, project_root: str, language: str = "python") -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "name": project_name,
            "root": project_root,
            "language": language,
        },
        "master_plan": {"phases": []},
        "current_phase_id": None,
        "current_sub_task_id": None,
        "sessions_index": [],
        "avoid_registry": [],
        "insights": [],
        "budget": {
            "session_type": "BUILD",
            "session_budget_tokens": 75_000,
            "tokens_consumed_this_session": 0,
        },
    }


def validate_dna_structure(dna: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if dna.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"Unsupported schema_version: {dna.get('schema_version')}")

    project = dna.get("project")
    if not isinstance(project, dict) or not project.get("name"):
        errors.append("project.name is required")

    phases = dna.get("master_plan", {}).get("phases", [])
    if not isinstance(phases, list):
        errors.append("master_plan.phases must be a list")
        return errors

    phase_ids: set[str] = set()
    for i, phase in enumerate(phases):
        pid = phase.get("id")
        if not pid:
            errors.append(f"Phase at index {i} missing id")
            continue
        if pid in phase_ids:
            errors.append(f"Duplicate phase id: {pid}")
        phase_ids.add(pid)

        status = phase.get("status", PhaseStatus.PENDING.value)
        if status not in {s.value for s in PhaseStatus}:
            errors.append(f"Phase {pid} has invalid status: {status}")

        for j, st in enumerate(phase.get("sub_tasks", [])):
            st_status = st.get("status", SubTaskStatus.PENDING.value)
            if st_status not in {s.value for s in SubTaskStatus}:
                errors.append(f"Sub-task {j} in {pid} invalid status: {st_status}")

    current = dna.get("current_phase_id")
    if current and current not in phase_ids:
        errors.append(f"current_phase_id {current} not in phases")

    if errors:
        raise DnaValidationError("; ".join(errors))
    return errors
