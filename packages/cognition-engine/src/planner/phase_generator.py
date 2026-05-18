"""Generate master plan phase sequences."""

from __future__ import annotations

from typing import Any

from src.core.constants import PhaseStatus, SessionType, TaskStatus

_PHASE_TEMPLATES = [
    ("Discovery", "Understand scope, stack, and constraints"),
    ("Foundation", "Project structure, config, and tooling"),
    ("Core domain", "Primary business logic and APIs"),
    ("Data layer", "Persistence, models, and migrations"),
    ("API surface", "REST/GraphQL endpoints and contracts"),
    ("Authentication", "Auth, sessions, and permissions"),
    ("Integration", "External services and adapters"),
    ("Testing", "Unit, integration, and fixture coverage"),
    ("Observability", "Logging, metrics, and tracing"),
    ("Performance", "Profiling and optimization"),
    ("Security review", "Threat model and hardening"),
    ("Documentation", "README, API docs, and examples"),
    ("CLI / UX", "Developer and operator experience"),
    ("Deployment", "CI/CD and environment config"),
    ("Monitoring", "Production readiness checks"),
    ("Refinement", "Tech debt and polish"),
    ("Feature expansion", "Secondary user flows"),
    ("Load & resilience", "Stress tests and failure modes"),
    ("Compliance", "Policies, licensing, and audit trail"),
    ("Release", "Versioning, changelog, and handoff"),
    ("Stabilization", "Bug bash and regression fixes"),
    ("Knowledge transfer", "Runbooks and onboarding docs"),
    ("Maintenance", "Backlog grooming and support hooks"),
    ("Analytics", "Usage metrics and feedback loops"),
    ("Orchestration", "Workflow automation and agents"),
    ("Platform hooks", "Integrations with Cognition Engine"),
    ("Hardening pass", "Final security and cost review"),
    ("Launch", "Go-live checklist"),
    ("Post-launch", "Hotfix runway and monitoring"),
    ("Retrospective", "Lessons learned and DNA updates"),
]


def _phase(
    num: int,
    name: str,
    description: str,
    *,
    status: str | None = None,
    estimated_tokens: int = 12_000,
) -> dict[str, Any]:
    pid = f"PHASE_{num:02d}"
    st = status or (PhaseStatus.IN_PROGRESS.value if num == 1 else PhaseStatus.NOT_STARTED.value)
    return {
        "id": pid,
        "name": name,
        "description": description,
        "status": st,
        "completion_score": 0,
        "sessions_used": 0,
        "tokens_consumed": 0,
        "estimated_tokens": estimated_tokens,
        "budget_tokens": int(estimated_tokens * 1.2),
        "deliverables": [],
        "dependencies": [f"PHASE_{num - 1:02d}"] if num > 1 else [],
        "blocked_by": [],
        "sub_tasks": [
            {
                "id": f"P{num}_T1",
                "name": f"{name} — primary",
                "status": TaskStatus.IN_PROGRESS.value if num == 1 else TaskStatus.PENDING.value,
                "progress": 0,
                "files_modified": [],
                "completion_criteria": "Deliverable reviewed and merged",
                "estimated_tokens": estimated_tokens // 2,
                "next_action": description,
            },
            {
                "id": f"P{num}_T2",
                "name": f"{name} — validation",
                "status": TaskStatus.PENDING.value,
                "progress": 0,
                "files_modified": [],
                "completion_criteria": "Tests pass",
                "estimated_tokens": estimated_tokens // 2,
            },
        ],
        "state_history": [],
        "phase_type": SessionType.BUILD.value,
        "insights_generated": [],
    }


def generate_simple_plan(project_name: str, language: str = "python") -> list[dict[str, Any]]:
    _ = project_name, language
    return [_phase(i + 1, name, desc) for i, (name, desc) in enumerate(_PHASE_TEMPLATES[:8])]


def generate_goal_plan(
    goal: str,
    *,
    num_phases: int = 24,
    language: str = "python",
) -> list[dict[str, Any]]:
    _ = language
    count = max(8, min(30, num_phases))
    phases: list[dict[str, Any]] = []
    for i in range(count):
        if i < len(_PHASE_TEMPLATES):
            name, desc = _PHASE_TEMPLATES[i]
        else:
            name, desc = (f"Milestone {i + 1}", f"Advance: {goal[:80]}")
        phase = _phase(i + 1, name, f"{desc}. See project goal in bootstrap (GOAL.md / DNA).")
        phases.append(phase)
    return phases
