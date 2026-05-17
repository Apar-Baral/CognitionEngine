from __future__ import annotations

from typing import Any

from cognition_engine.core.constants import PhaseStatus, SubTaskStatus


def _phase(
    num: int,
    name: str,
    description: str,
    sub_tasks: list[tuple[str, str, str]],
    estimated_tokens: int = 50_000,
) -> dict[str, Any]:
    pid = f"PHASE_{num:02d}"
    return {
        "id": pid,
        "name": name,
        "description": description,
        "status": PhaseStatus.PENDING.value if num > 1 else PhaseStatus.IN_PROGRESS.value,
        "completion_score": 0,
        "estimated_tokens": estimated_tokens,
        "sub_tasks": [
            {
                "id": f"{pid}_T{i + 1}",
                "name": st_name,
                "status": SubTaskStatus.PENDING.value
                if i > 0
                else SubTaskStatus.IN_PROGRESS.value,
                "progress": 0,
                "next_action": action,
                "estimated_tokens": estimated_tokens // max(len(sub_tasks), 1),
            }
            for i, (st_name, action, _) in enumerate(sub_tasks)
        ],
    }


def generate_simple_plan(project_name: str, language: str = "python") -> list[dict[str, Any]]:
    """Generic 8-phase plan for arbitrary projects."""
    return [
        _phase(1, "Discovery", "Scan codebase and define scope", [
            ("Inventory", "List main modules and entry points", ""),
            ("Constraints", "Document stack and conventions", ""),
        ]),
        _phase(2, "Foundation", "Core project structure", [
            ("Scaffold", "Ensure build/test tooling works", ""),
            ("Config", "Centralize configuration", ""),
        ]),
        _phase(3, "Core features", "Implement primary user flows", [
            ("Domain model", "Implement core types and APIs", ""),
            ("Integration", "Wire modules together", ""),
        ]),
        _phase(4, "Quality", "Tests and hardening", [
            ("Unit tests", "Cover critical paths", ""),
            ("CI", "Automate test runs", ""),
        ]),
        _phase(5, "Documentation", "Docs and examples", [
            ("README", "Update usage docs", ""),
            ("Examples", "Add runnable examples", ""),
        ]),
        _phase(6, "Performance", "Optimize hot paths", [
            ("Profile", "Identify bottlenecks", ""),
            ("Optimize", "Apply targeted fixes", ""),
        ]),
        _phase(7, "Security", "Review and harden", [
            ("Audit", "Run security checklist", ""),
            ("Fix", "Address findings", ""),
        ]),
        _phase(8, "Release", "Ship v1", [
            ("Polish", "Final review and changelog", ""),
            ("Publish", "Tag release and announce", ""),
        ]),
    ]


def generate_meta_tool_plan() -> list[dict[str, Any]]:
    """10-phase plan for building Cognition Engine itself (dogfood)."""
    return [
        _phase(1, "DNA & memory", "Project DNA and session persistence", [
            ("Schema", "Implement dna.json schema and loader", ""),
            ("Sessions", "JSONL session store and ce init/start/end", ""),
        ], 40_000),
        _phase(2, "Bootstrap", "Context compiler and bootstrap packet", [
            ("Compiler", "Strategic + tactical context under 2k tokens", ""),
            ("CLI", "ce status and progress map", ""),
        ], 35_000),
        _phase(3, "Adapters", "Cursor and Claude Code integration", [
            ("Cursor", "Write .cognition bootstrap + rules snippet", ""),
            ("Claude", "CLAUDE.md sync adapter", ""),
        ], 30_000),
        _phase(4, "Token budgets", "Manual tracking and budget zones", [
            ("Budget", "ce budget and zone warnings", ""),
            ("Logging", "Token fields in session logs", ""),
        ], 35_000),
        _phase(5, "Hallucination shield", "Stage-1 import/symbol validation", [
            ("Truth index", "AST symbol index for Python", ""),
            ("Validator", "Import check + avoid register", ""),
        ], 45_000),
        _phase(6, "Scanner", "Project scan and language detect", [
            ("Detect", "Language and file tree scan", ""),
            ("Index", "Refresh truth index on demand", ""),
        ], 30_000),
        _phase(7, "Planner upgrade", "Smarter phase generation", [
            ("Heuristics", "Task sizing from project scan", ""),
            ("Deps", "Phase dependency ordering", ""),
        ], 40_000),
        _phase(8, "Insights", "Session pattern analysis", [
            ("Synthesizer", "Basic insights from sessions_index", ""),
            ("ce insights", "CLI command for trends", ""),
        ], 35_000),
        _phase(9, "Polish", "UX and error messages", [
            ("CLI", "Completions and help text", ""),
            ("Tests", "Integration test suite", ""),
        ], 30_000),
        _phase(10, "Launch", "Docs and first users", [
            ("Docs", "Quickstart and landing", ""),
            ("Dogfood", "10+ real sessions on this repo", ""),
        ], 25_000),
    ]
