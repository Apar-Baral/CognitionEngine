"""
DNA validation: JSON Schema + semantic checks.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

import jsonschema
from jsonschema import Draft7Validator

from src.core.constants import PhaseStatus, TaskStatus
from src.dna.schema import DNA_SCHEMA

ValidationSeverity = Literal["ERROR", "WARNING"]

_PHASE_ID_RE = re.compile(r"^PHASE_(\d{2})$")
_SUBTASK_ID_RE = re.compile(r"^P(\d+)_T(\d+)$")


class DNAValidator:
    """Validates DNA dictionaries against schema and business rules."""

    def __init__(self) -> None:
        self._validator = Draft7Validator(DNA_SCHEMA)

    def validate(self, dna: dict[str, Any]) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []

        for err in sorted(self._validator.iter_errors(dna), key=lambda e: list(e.path)):
            path = "/" + "/".join(str(p) for p in err.path) if err.path else "/"
            errors.append(
                {
                    "path": path,
                    "message": err.message,
                    "severity": "ERROR",
                }
            )

        if not any(e["severity"] == "ERROR" for e in errors):
            errors.extend(self._semantic_validate(dna))

        return errors

    def validate_file(self, path: Path | str) -> list[dict[str, Any]]:
        file_path = Path(path)
        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            return [
                {
                    "path": str(file_path),
                    "message": f"Invalid JSON: {e}",
                    "severity": "ERROR",
                }
            ]
        if not isinstance(data, dict):
            return [
                {
                    "path": str(file_path),
                    "message": "DNA root must be a JSON object",
                    "severity": "ERROR",
                }
            ]
        return self.validate(data)

    def _semantic_validate(self, dna: dict[str, Any]) -> list[dict[str, Any]]:
        errors: list[dict[str, Any]] = []
        phases = dna.get("master_plan", {}).get("phase_sequence", [])
        phase_ids = [p.get("id") for p in phases if isinstance(p, dict)]
        phase_id_set = set(phase_ids)

        # Phase ID format and sequential numbering
        phase_numbers: list[int] = []
        for pid in phase_ids:
            m = _PHASE_ID_RE.match(pid or "")
            if m:
                phase_numbers.append(int(m.group(1)))
        if phase_numbers:
            expected = list(range(1, len(phase_numbers) + 1))
            if sorted(phase_numbers) != expected:
                errors.append(
                    {
                        "path": "/master_plan/phase_sequence",
                        "message": (
                            f"Phase IDs must be sequential PHASE_01..PHASE_{len(expected):02d} "
                            f"with no gaps; got numbers {sorted(phase_numbers)}"
                        ),
                        "severity": "ERROR",
                    }
                )

        # Duplicate phase IDs
        if len(phase_ids) != len(phase_id_set):
            errors.append(
                {
                    "path": "/master_plan/phase_sequence",
                    "message": "Duplicate phase IDs in phase_sequence",
                    "severity": "ERROR",
                }
            )

        # Dependency references
        for i, phase in enumerate(phases):
            if not isinstance(phase, dict):
                continue
            pid = phase.get("id", f"index_{i}")
            for dep in phase.get("dependencies", []):
                if dep not in phase_id_set:
                    errors.append(
                        {
                            "path": f"/master_plan/phase_sequence/{i}/dependencies",
                            "message": f"Phase {pid} depends on unknown phase {dep}",
                            "severity": "ERROR",
                        }
                    )

        # current_phase index
        mp = dna.get("master_plan", {})
        current = mp.get("current_phase")
        total = mp.get("total_phases")
        if isinstance(current, int) and phases:
            if current < 1 or current > len(phases):
                errors.append(
                    {
                        "path": "/master_plan/current_phase",
                        "message": (
                            f"current_phase {current} out of range "
                            f"(1..{len(phases)})"
                        ),
                        "severity": "ERROR",
                    }
                )
            if total is not None and total != len(phases):
                errors.append(
                    {
                        "path": "/master_plan/total_phases",
                        "message": (
                            f"total_phases ({total}) must match "
                            f"phase_sequence length ({len(phases)})"
                        ),
                        "severity": "ERROR",
                    }
                )

        # Architecture edges
        nodes = dna.get("architecture_graph", {}).get("nodes", [])
        edges = dna.get("architecture_graph", {}).get("edges", [])
        node_ids = {n.get("id") for n in nodes if isinstance(n, dict)}
        for j, edge in enumerate(edges):
            if not isinstance(edge, dict):
                continue
            for end in ("source", "target"):
                ref = edge.get(end)
                if ref and ref not in node_ids:
                    errors.append(
                        {
                            "path": f"/architecture_graph/edges/{j}/{end}",
                            "message": f"Edge references unknown node {ref}",
                            "severity": "ERROR",
                        }
                    )

        # total_sessions vs sessions_index
        proj = dna.get("project", {})
        sessions = dna.get("sessions_index", [])
        if proj.get("total_sessions") != len(sessions):
            errors.append(
                {
                    "path": "/project/total_sessions",
                    "message": (
                        f"total_sessions ({proj.get('total_sessions')}) must equal "
                        f"sessions_index length ({len(sessions)})"
                    ),
                    "severity": "ERROR",
                }
            )

        # Sub-task ID format and completion consistency
        for i, phase in enumerate(phases):
            if not isinstance(phase, dict):
                continue
            pid = phase.get("id", "")
            pm = _PHASE_ID_RE.match(pid)
            phase_num = int(pm.group(1)) if pm else None
            sub_tasks = phase.get("sub_tasks", [])
            for j, st in enumerate(sub_tasks):
                if not isinstance(st, dict):
                    continue
                st_id = st.get("id", "")
                sm = _SUBTASK_ID_RE.match(st_id)
                if phase_num and sm:
                    if int(sm.group(1)) != phase_num:
                        errors.append(
                            {
                                "path": (
                                    f"/master_plan/phase_sequence/{i}/"
                                    f"sub_tasks/{j}/id"
                                ),
                                "message": (
                                    f"Sub-task {st_id} must use phase number "
                                    f"{phase_num} (P{phase_num}_T{{n}})"
                                ),
                                "severity": "ERROR",
                            }
                        )
                elif st_id:
                    errors.append(
                        {
                            "path": (
                                f"/master_plan/phase_sequence/{i}/sub_tasks/{j}/id"
                            ),
                            "message": (
                                f"Sub-task id {st_id} must match P{{n}}_T{{m}} format"
                            ),
                            "severity": "WARNING",
                        }
                    )

            if sub_tasks:
                all_done = all(
                    isinstance(st, dict)
                    and st.get("status") == TaskStatus.DONE.value
                    for st in sub_tasks
                )
                status = phase.get("status")
                score = phase.get("completion_score", 0)
                if all_done and status == PhaseStatus.NOT_STARTED.value:
                    errors.append(
                        {
                            "path": f"/master_plan/phase_sequence/{i}/status",
                            "message": (
                                f"Phase {pid}: all sub-tasks DONE but phase "
                                f"status is {status}"
                            ),
                            "severity": "WARNING",
                        }
                    )
                if all_done and status not in (
                    PhaseStatus.IN_REVIEW.value,
                    PhaseStatus.COMPLETED.value,
                ):
                    errors.append(
                        {
                            "path": f"/master_plan/phase_sequence/{i}/status",
                            "message": (
                                f"Phase {pid}: all sub-tasks DONE; phase should be "
                                f"at least IN_REVIEW (currently {status})"
                            ),
                            "severity": "WARNING",
                        }
                    )
                if all_done and score < 90:
                    errors.append(
                        {
                            "path": f"/master_plan/phase_sequence/{i}/completion_score",
                            "message": (
                                f"Phase {pid}: all sub-tasks DONE but "
                                f"completion_score is only {score}"
                            ),
                            "severity": "WARNING",
                        }
                    )

        return errors


def validate(dna: dict[str, Any]) -> list[dict[str, Any]]:
    return DNAValidator().validate(dna)


__all__ = ["DNAValidator", "validate"]
