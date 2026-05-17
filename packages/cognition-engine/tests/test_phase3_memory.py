"""Phase 3 verification tests — memory system."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.dna.loader import DNALoader
from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery
from src.memory.metrics_store import MetricsStore
from src.memory.operational_memory import OperationalMemory
from src.memory.session_store import SessionStore
from src.memory.strategic_memory import StrategicMemory
from src.memory.tactical_memory import TacticalMemory
from tests.dna_fixtures import minimal_valid_dna


def _setup_dna(tmp_path: Path) -> tuple[DNALoader, DNAQuery, DNAMutator]:
    (tmp_path / ".cognition").mkdir(exist_ok=True)
    loader = DNALoader(tmp_path)
    loader.save(minimal_valid_dna())
    query = DNAQuery(loader)
    mutator = DNAMutator(loader)
    return loader, query, mutator


def test_strategic_memory_project_summary(tmp_path: Path):
    _, query, _ = _setup_dna(tmp_path)
    sm = StrategicMemory(query)
    summary = sm.get_project_summary()
    assert summary["project_name"] == "test-project"
    assert summary["current_phase_id"] == "PHASE_01"
    assert "overall_completion_percentage" in summary
    assert summary["total_phases"] == 2


def test_tactical_memory_active_context(tmp_path: Path):
    _, query, _ = _setup_dna(tmp_path)
    tm = TacticalMemory(query, "PHASE_01")
    ctx = tm.get_active_context()
    assert ctx["found"] is True
    assert ctx["phase_id"] == "PHASE_01"
    assert len(ctx["sub_tasks"]) == 2


def test_operational_memory_summary(tmp_path: Path):
    op = OperationalMemory(1, tmp_path, "BUILD", budget_tokens=50_000)
    op.log_api_call("claude-sonnet", "anthropic", 1000, 500, purpose="P1_T1")
    op.log_api_call("claude-sonnet", "anthropic", 800, 400)
    op.log_file_operation("src/main.py", "read", "aaa", "aaa")
    op.log_file_operation("src/main.py", "write", "aaa", "bbb")
    summary = op.get_session_summary()
    assert summary["tokens"]["total"] == 2700
    assert summary["api_calls_count"] == 2
    assert "src/main.py" in summary["files_modified"]


def test_session_store_roundtrip(tmp_path: Path):
    store = SessionStore(tmp_path, "test-project")
    sid = store.create_session(phase_id="PHASE_01")
    store.write_event(sid, "test_event", {"foo": "bar"})
    events = store.get_session(sid)
    assert len(events) >= 2
    assert any(e.get("event_type") == "test_event" for e in events)
    store.close_session(sid, {"efficiency_score": 85, "tokens": {"total": 1000}})
    recent = store.get_recent_sessions(1)
    assert recent[0]["session_id"] == sid


def test_metrics_store_history_and_trend(tmp_path: Path):
    ms = MetricsStore(tmp_path, "test-project")
    ms.record_metric("tokens_per_session", 5000.0, session_id=1)
    ms.record_metric("tokens_per_session", 6000.0, session_id=2)
    history = ms.get_metric_history("tokens_per_session")
    assert len(history) == 2
    trend = ms.get_trend("tokens_per_session", window_hours=48)
    assert "ema" in trend
    assert trend["direction"] in ("increasing", "decreasing", "stable")


def test_operational_hallucination_in_summary(tmp_path: Path):
    op = OperationalMemory(2, tmp_path, "BUILD")
    op.log_hallucination(
        "import_invention",
        "auth.py",
        "from flask_magic import x",
        "from flask_login import x",
        stage=1,
        auto_corrected=True,
    )
    summary = op.get_session_summary()
    assert summary["hallucinations_caught"] == 1
    assert summary["hallucinations_by_category"]["import_invention"] == 1


def test_session_store_find_by_date(tmp_path: Path):
    store = SessionStore(tmp_path, "test-project")
    sid = store.create_session()
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    end = datetime.now(timezone.utc) + timedelta(hours=1)
    found = store.find_by_date(start, end)
    assert any(e["session_id"] == sid for e in found)
