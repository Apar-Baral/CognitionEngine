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

_XSS_SCANNER_PHASES = [
    (
        "Scope and safety controls",
        "Define authorized target rules, rate limits, denylist handling, and safe defaults.",
        [
            "CLI accepts a target URL/scope file",
            "Scan refuses private/unsafe targets unless explicitly allowed",
        ],
    ),
    (
        "CLI project skeleton",
        "Build command surface, config loading, output formats, and structured logging.",
        ["`scan` command runs from terminal", "JSON and human-readable output modes exist"],
    ),
    (
        "URL normalization and crawling",
        "Normalize URLs, discover same-scope links, collect forms, and extract query parameters.",
        ["Crawler respects scope and depth", "Forms and URL params are stored as test candidates"],
    ),
    (
        "Payload library and mutation engine",
        "Create reflected, attribute, script-context, and DOM XSS payload mutations.",
        ["Payloads are tagged by context", "User-supplied payload files can be loaded"],
    ),
    (
        "HTTP runner and rate limiter",
        "Implement async requests, retries, headers, proxy support, timeouts, and throttling.",
        ["Concurrent scanner has bounded rate", "Proxy and custom headers work"],
    ),
    (
        "Reflection and context detection",
        "Detect payload reflection and classify HTML, attribute, JS, URL, and text contexts.",
        ["Scanner reports reflected input location", "Context classifier drives payload choice"],
    ),
    (
        "Browser verification",
        "Use a headless browser to verify executable XSS instead of reflection only.",
        ["Alert/callback/canary verification works", "False positives are marked unverified"],
    ),
    (
        "Learning and payload prioritization",
        "Track payload success per context and prioritize future attempts from scan history.",
        [
            "Payload success metrics are persisted",
            "Scanner reorders payloads by context effectiveness",
        ],
    ),
    (
        "Reporting and evidence",
        "Generate findings with evidence, reproduction command, severity, and remediation.",
        ["Findings include proof and confidence", "Reports export to JSON/Markdown"],
    ),
    (
        "Authentication/session support",
        "Support cookies, bearer tokens, header profiles, session reuse, and auth scans.",
        ["Authenticated requests can be replayed", "Secrets are excluded from reports/logs"],
    ),
    (
        "Test lab and regression suite",
        "Add vulnerable local fixtures and automated crawler/payload/verification tests.",
        ["Local vulnerable app fixtures exist", "Regression tests cover true/false positives"],
    ),
    (
        "Packaging and release",
        "Package the scanner as an installable CLI with docs, examples, and CI checks.",
        ["`pipx install`/entry point works", "README documents authorized-use workflow"],
    ),
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


def _custom_phase(
    num: int,
    name: str,
    description: str,
    deliverables: list[str],
    *,
    estimated_tokens: int = 12_000,
) -> dict[str, Any]:
    phase = _phase(num, name, description, estimated_tokens=estimated_tokens)
    phase["deliverables"] = deliverables
    phase["sub_tasks"] = [
        {
            "id": f"P{num}_T1",
            "name": f"{name} — implementation",
            "status": TaskStatus.IN_PROGRESS.value if num == 1 else TaskStatus.PENDING.value,
            "progress": 0,
            "files_modified": [],
            "completion_criteria": deliverables[0],
            "estimated_tokens": int(estimated_tokens * 0.55),
            "next_action": description,
        },
        {
            "id": f"P{num}_T2",
            "name": f"{name} — validation",
            "status": TaskStatus.PENDING.value,
            "progress": 0,
            "files_modified": [],
            "completion_criteria": deliverables[-1],
            "estimated_tokens": int(estimated_tokens * 0.30),
            "next_action": f"Prove: {deliverables[-1]}",
        },
        {
            "id": f"P{num}_T3",
            "name": f"{name} — documentation",
            "status": TaskStatus.PENDING.value,
            "progress": 0,
            "files_modified": [],
            "completion_criteria": "Docs/examples explain how to use this capability safely",
            "estimated_tokens": int(estimated_tokens * 0.15),
        },
    ]
    return phase


def _looks_like_xss_scanner(goal: str) -> bool:
    text = goal.lower()
    return (
        "xss" in text
        and any(term in text for term in ("scanner", "scan", "vulnerability", "bug bounty"))
    ) or ("bug bounty" in text and "cli" in text)


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
    if _looks_like_xss_scanner(goal):
        wanted = max(8, min(len(_XSS_SCANNER_PHASES), num_phases))
        return [
            _custom_phase(i + 1, name, desc, deliverables, estimated_tokens=10_000 + i * 1_500)
            for i, (name, desc, deliverables) in enumerate(_XSS_SCANNER_PHASES[:wanted])
        ]
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
