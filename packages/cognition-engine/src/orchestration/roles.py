"""Specialized agent roles and task decomposition."""

from __future__ import annotations

from typing import Any

ROLE_PROMPTS: dict[str, str] = {
    "architect": "Architect: design and interfaces only.",
    "backend": "Backend Dev: APIs and server implementation.",
    "frontend": "Frontend Dev: UI and client code.",
    "security": "Security Reviewer: audit only.",
    "test": "Test Writer: tests and fixtures.",
    "docs": "Doc Writer: documentation updates.",
    "refactor": "Refactor: structure without behavior change.",
}


def decompose_subtasks(phase: dict[str, Any]) -> list[dict[str, Any]]:
    units = []
    for st in phase.get("sub_tasks", []):
        units.append(
            {
                "id": st.get("id"),
                "name": st.get("name"),
                "estimated_tokens": st.get("estimated_tokens", 25000),
                "contract": st.get("next_action") or st.get("name"),
            }
        )
    return units


def merge_outputs(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    files: dict[str, str] = {}
    conflicts = []
    for o in outputs:
        for path, body in (o.get("files") or {}).items():
            if path in files and files[path] != body:
                conflicts.append(path)
            files[path] = body
    return {"files": files, "conflicts": conflicts, "strategy": "manual" if conflicts else "clean"}
