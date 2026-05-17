"""Phase 8 — progress visualizer and strategic navigator."""

from __future__ import annotations

from datetime import date
from io import StringIO
from pathlib import Path

import networkx as nx
import pytest
from rich.console import Console

from src.core.constants import PhaseStatus, TaskStatus
from src.core.exceptions import DependencyCycleError, InvalidTransitionError, TransitionBlockedError
from src.core.types import BudgetStatus
from src.dna.loader import DNALoader
from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery
from src.navigator.complexity_forecaster import ComplexityForecaster
from src.navigator.debt_detector import DebtDetector
from src.navigator.dependency_resolver import DependencyResolver
from src.navigator.phase_tracker import PhaseTracker
from src.navigator.recommendation_engine import RecommendationEngine
from src.visualization import ascii_art, dashboard, heat_maps, progress_bars, timeline


def _render_str(renderable) -> str:
    buf = StringIO()
    Console(file=buf, width=120, force_terminal=True, legacy_windows=False).print(renderable)
    return buf.getvalue()


def _mock_phases() -> list[dict]:
    return [
        {
            "id": "PHASE_01",
            "name": "Foundation",
            "status": PhaseStatus.COMPLETED.value,
            "completion_score": 100,
            "completed": "2026-01-10",
            "sessions_used": 2,
            "dependencies": [],
            "blocked_by": [],
            "sub_tasks": [],
        },
        {
            "id": "PHASE_02",
            "name": "Core API",
            "status": PhaseStatus.IN_PROGRESS.value,
            "completion_score": 65,
            "dependencies": ["PHASE_01"],
            "blocked_by": [],
            "sub_tasks": [
                {
                    "id": "P2_T1",
                    "name": "Handlers",
                    "status": TaskStatus.IN_PROGRESS.value,
                    "progress": 65,
                    "estimated_tokens": 10000,
                }
            ],
        },
        {
            "id": "PHASE_03",
            "name": "Auth",
            "status": PhaseStatus.BLOCKED.value,
            "completion_score": 10,
            "dependencies": ["PHASE_02"],
            "blocked_by": ["PHASE_02 incomplete"],
            "sub_tasks": [],
        },
        {
            "id": "PHASE_04",
            "name": "Deploy",
            "status": PhaseStatus.NOT_STARTED.value,
            "completion_score": 0,
            "dependencies": ["PHASE_03"],
            "blocked_by": [],
            "sub_tasks": [],
        },
    ]


def test_render_phase_progress_map():
    phases = _mock_phases()
    panel = progress_bars.render_phase_progress_map(
        phases,
        project_name="TestApp",
        current_phase_index=2,
        overall_completion=41.0,
        total_sessions=5,
        total_tokens=48000,
        completion_trend=[10, 20, 30, 35, 41],
    )
    out = _render_str(panel)
    assert "PHASE_01" in out
    assert "PHASE_02" in out
    assert "HERE" in out
    assert "Foundation" in out


def test_render_compact_progress():
    line = progress_bars.render_compact_progress(
        _mock_phases(), current_index=2, overall_completion=41.0, max_width=100
    )
    assert "41%" in line
    assert "PHASE_02" in line


def test_render_live_dashboard():
    status = BudgetStatus(
        tokens_used=48200,
        tokens_remaining=26800,
        percentage_used=64.3,
        current_zone="yellow",
        estimated_cost=1.21,
        session_duration_seconds=1800,
        burn_rate_per_minute=1200,
        projected_exhaustion_time="22 min",
    )
    state = {
        "session_id": 7,
        "phase_id": "PHASE_02",
        "sub_task_id": "P2_T1",
        "efficiency_score": 0.82,
        "efficiency_trend": [0.7, 0.75, 0.8, 0.82],
        "agents": [{"type": "backend_dev", "model": "claude-sonnet", "status": "active", "tokens": 12000}],
        "hallucinations_caught": 2,
        "hallucination_categories": {"import_invention": 1},
        "files_modified": ["api/handlers.py"],
        "shield_status": "active",
        "budget_status": status,
    }
    out = _render_str(dashboard.render_live_dashboard(state, project_name="TestApp", budget=status))
    assert "Session #7" in out
    assert "PHASE_02" in out
    assert "64" in out or "48200" in out


def test_render_token_heat_map():
    data = {
        "auth/models.py": 12400,
        "api/handlers.py": 9200,
        "utils/helpers.py": 4500,
    }
    out = _render_str(heat_maps.render_token_heat_map(data))
    assert "auth/models.py" in out
    assert "12,400" in out or "12400" in out
    assert "26" in out or "%" in out


def test_phase_tracker_transitions(tmp_path: Path):
    from tests.dna_fixtures import minimal_valid_dna

    dna = minimal_valid_dna()
    cog = tmp_path / ".cognition"
    cog.mkdir()
    (cog / "dna.json").write_text(__import__("json").dumps(dna), encoding="utf-8")
    loader = DNALoader(tmp_path)
    query = DNAQuery(loader)
    mutator = DNAMutator(loader)
    tracker = PhaseTracker(query, mutator)

    progress = tracker.calculate_phase_progress("PHASE_01")
    assert 0 <= progress <= 100

    with pytest.raises(InvalidTransitionError):
        tracker.transition_phase("PHASE_01", PhaseStatus.NOT_STARTED, session_id=1)

    phase1 = dna["master_plan"]["phase_sequence"][0]
    for st in phase1["sub_tasks"]:
        st["status"] = TaskStatus.DONE.value
        st["progress"] = 100
    phase1["completion_score"] = 100
    phase1["deliverables"] = []
    loader.save(dna)
    query.refresh()

    tracker.transition_phase("PHASE_01", PhaseStatus.COMPLETED, session_id=3)
    query.refresh()
    assert query.get_phase_by_id("PHASE_01")["status"] == PhaseStatus.COMPLETED.value


def test_dependency_critical_path_and_blockers():
    phases = _mock_phases()

    class _Q:
        def refresh(self):
            return {"master_plan": {"phase_sequence": phases}}

        def get_phase_by_id(self, pid):
            return next((p for p in phases if p["id"] == pid), None)

    resolver = DependencyResolver(_Q())  # type: ignore[arg-type]
    path, tokens = resolver.find_critical_path()
    assert "PHASE_01" in path
    assert tokens > 0

    blockers = resolver.find_blockers("PHASE_03")
    assert any(b["phase_id"] == "PHASE_02" for b in blockers)

    dependents = resolver.what_depends_on("PHASE_02")
    assert any(d["phase_id"] == "PHASE_03" for d in dependents)


def test_detect_circular_dependencies():
    phases = [
        {"id": "PHASE_01", "dependencies": ["PHASE_02"], "estimated_tokens": 1000},
        {"id": "PHASE_02", "dependencies": ["PHASE_01"], "estimated_tokens": 1000},
    ]

    class _Q:
        def refresh(self):
            return {"master_plan": {"phase_sequence": phases}}

        def get_phase_by_id(self, pid):
            return next((p for p in phases if p["id"] == pid), None)

    resolver = DependencyResolver(_Q())  # type: ignore[arg-type]
    cycles = resolver.detect_circular_dependencies()
    assert len(cycles) >= 1
    with pytest.raises(DependencyCycleError):
        resolver.get_execution_order()


def test_debt_scan(tmp_path: Path):
    src = tmp_path / "app.py"
    src.write_text("# TODO: fix this\n# FIXME: urgent\n", encoding="utf-8")
    from tests.dna_fixtures import minimal_valid_dna

    cog = tmp_path / ".cognition"
    cog.mkdir()
    (cog / "dna.json").write_text(__import__("json").dumps(minimal_valid_dna()), encoding="utf-8")
    query = DNAQuery(DNALoader(tmp_path))
    detector = DebtDetector(query, tmp_path)
    items = detector.scan_for_debt()
    types = {i["type"] for i in items}
    assert "todo" in types
    assert "fixme" in types


def test_recommendation_engine():
    phases = _mock_phases()

    class _Q:
        def refresh(self):
            return {
                "master_plan": {"phase_sequence": phases, "current_phase": 2},
                "project": {"name": "t"},
                "sessions_index": [],
                "deviation_history": [],
            }

        def get_current_phase(self):
            return phases[1]

        def get_blocked_phases(self):
            return [phases[2]]

        def get_next_executable_phase(self):
            return None

        def get_phases_depending_on(self, pid):
            return [p for p in phases if pid in p.get("dependencies", [])]

        def get_phase_by_id(self, pid):
            return next((p for p in phases if p["id"] == pid), None)

        def calculate_project_completion(self):
            return 41.0

    q = _Q()
    loader = DNALoader.__new__(DNALoader)
    mutator = DNAMutator.__new__(DNAMutator)
    tracker = PhaseTracker(q, mutator)  # type: ignore[arg-type]
    resolver = DependencyResolver(q)  # type: ignore[arg-type]
    forecaster = ComplexityForecaster(q, Path("."))  # type: ignore[arg-type]
    debt = DebtDetector(q, Path("."))  # type: ignore[arg-type]
    engine = RecommendationEngine(tracker, resolver, forecaster, debt, q)  # type: ignore[arg-type]
    recs = engine.get_recommendations()
    assert recs
    assert recs[0]["priority"] >= 5
    assert "rationale" in recs[0]
    assert engine.get_next_session_prompt()


def test_ascii_primitives():
    bar = ascii_art.create_progress_bar(75, width=10)
    assert bar is not None
    assert ascii_art.create_sparkline([1, 2, 5, 3, 8], width=5)
    box = ascii_art.create_box("hello", title="T")
    assert "hello" in box


def test_gantt_and_blocker_report():
    phases = _mock_phases()
    for p in phases:
        p["started"] = "2026-01-01"
    out = _render_str(timeline.render_gantt_chart(phases, critical_path=["PHASE_01", "PHASE_02"], today=date(2026, 1, 15)))
    assert "PHASE_02" in out
    blocked = progress_bars.render_blocker_report([phases[2]])
    assert "PHASE_03" in _render_str(blocked)
