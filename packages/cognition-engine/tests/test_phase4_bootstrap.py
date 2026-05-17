"""Phase 4 verification tests — session bootstrap system."""

from __future__ import annotations

from pathlib import Path

from src.bootstrap.avoid_register import AvoidRegister
from src.bootstrap.bootstrap_formatter import format_bootstrap, BootstrapParts
from src.bootstrap.bootstrap_generator import BootstrapGenerator, infer_session_type
from src.bootstrap.budget_predictor import BudgetPredictor
from src.bootstrap.context_compiler import ContextCompiler, estimate_tokens
from src.bootstrap.precompiler import Precompiler
from src.core.constants import BOOTSTRAP_MAX_TOKENS, COGNITION_DIR, SessionType
from src.dna.loader import DNALoader
from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery
from src.memory.metrics_store import MetricsStore
from src.memory.session_store import SessionStore
from src.memory.strategic_memory import StrategicMemory
from src.memory.tactical_memory import TacticalMemory
from tests.dna_fixtures import minimal_valid_dna


def _setup(tmp_path: Path) -> tuple[DNAQuery, DNAMutator, StrategicMemory, SessionStore, MetricsStore]:
    (tmp_path / ".cognition").mkdir(exist_ok=True)
    loader = DNALoader(tmp_path)
    loader.save(minimal_valid_dna())
    query = DNAQuery(loader)
    mutator = DNAMutator(loader)
    return (
        query,
        mutator,
        StrategicMemory(query),
        SessionStore(tmp_path, "test-project"),
        MetricsStore(tmp_path, "test-project"),
    )


def _generator(tmp_path: Path) -> BootstrapGenerator:
    query, mutator, strategic, sessions, metrics = _setup(tmp_path)
    tactical = TacticalMemory(query, "PHASE_01", mutator)
    avoid = AvoidRegister(query, mutator)
    compiler = ContextCompiler(strategic, tactical, project_root=tmp_path)
    predictor = BudgetPredictor(metrics, query)
    return BootstrapGenerator(
        strategic,
        tactical,
        compiler,
        avoid,
        predictor,
        query,
        session_store=sessions,
        project_root=tmp_path,
    )


def test_estimate_tokens():
    assert estimate_tokens("one two three four") >= 4


def test_context_compiler_within_budget(tmp_path: Path):
    query, _, strategic, _, _ = _setup(tmp_path)
    tactical = TacticalMemory(query, "PHASE_01")
    compiler = ContextCompiler(strategic, tactical, project_root=tmp_path)
    text = compiler.compile_context("Implement bootstrap", BOOTSTRAP_MAX_TOKENS)
    assert "SESSION BOOTSTRAP" in text
    assert "PHASE_01" in text
    assert "Coding standards:" in text
    assert estimate_tokens(text) <= BOOTSTRAP_MAX_TOKENS + 150


def test_avoid_register_relevance(tmp_path: Path):
    query, mutator, _, _, _ = _setup(tmp_path)
    reg = AvoidRegister(query, mutator)
    reg.add_hallucination(
        "import_invention",
        "flask_magic_auth",
        "flask_login",
        "Package does not exist",
        "src/auth/views.py",
    )
    reg.add_understood_file("src/auth/models.py")
    items = reg.get_relevant_avoid_items("auth views flask", limit=5)
    assert len(items) >= 1
    assert reg.is_file_understood("src/auth/models.py")


def test_budget_predictor_stages(tmp_path: Path):
    query, _, _, _, metrics = _setup(tmp_path)
    predictor = BudgetPredictor(metrics, query)
    for i in range(3):
        predictor.calibrate(SessionType.BUILD, "PHASE_01", 50_000 + i * 1000, session_id=i + 1)
    pred = predictor.predict(SessionType.BUILD, "PHASE_01", 4, "MEDIUM")
    assert pred["estimated_tokens"] > 0
    assert "confidence_interval" in pred
    assert "exact_match" in pred["basis"]
    budget = predictor.get_recommended_budget(pred)
    assert budget >= pred["estimated_tokens"]
    cost = predictor.get_cost_estimate(pred, "claude-sonnet")
    assert cost > 0


def test_bootstrap_format_exact(tmp_path: Path):
    parts = BootstrapParts(
        session_id="42",
        phase_id="PHASE_01",
        phase_name="Foundation",
        phase_completion=25.0,
        subtask_id="P1_T1",
        subtask_name="Setup",
        subtask_progress=50,
        objective="Wire bootstrap generator",
        previous_session_id="41",
        last_completed="Added memory layer",
        last_decisions=["Use SQLite for metrics"],
        last_files_modified=["src/main.py"],
        last_unfinished="Add formatter tests",
        relevant_files=[("src/bootstrap/generator.py", "Orchestrates session prep")],
        avoid_items=["Do not import flask_magic_auth"],
        predicted_tokens=50_000,
        recommended_budget=60_000,
        cost_estimate=1.21,
    )
    text = format_bootstrap(parts)
    assert "╔" in text and "╚" in text
    assert "SESSION #42" in text
    assert "📋 CURRENT MISSION" in text
    assert "Phase PHASE_01:" in text
    assert "📝 LAST SESSION (Session #41)" in text
    assert "📂 RELEVANT FILES" in text
    assert "⚠️ DO NOT REPEAT" in text
    assert "💰 BUDGET" in text
    assert "Predicted: 50,000 tokens" in text
    assert "Recommended Cap: 60,000 tokens" in text
    assert "Estimated Cost: $1.21" in text
    assert "Ready. Continue from where you left off." in text


def test_bootstrap_generator_preview_and_save(tmp_path: Path):
    gen = _generator(tmp_path)
    preview = gen.preview_bootstrap("Continue phase 1 task 1")
    assert preview["session_id"] == "PREVIEW"
    assert "SESSION #PREVIEW" in preview["context_text"]
    assert "📋 CURRENT MISSION" in preview["context_text"]
    assert preview["phase_id"] == "PHASE_01"
    assert preview["token_count"] <= BOOTSTRAP_MAX_TOKENS + 200

    saved = gen.generate_and_save("Continue phase 1 task 1")
    assert saved["session_id"] != "PREVIEW"
    assert f"SESSION #{saved['session_id']}" in saved["context_text"]
    bootstrap_md = tmp_path / COGNITION_DIR / "bootstrap.md"
    assert bootstrap_md.is_file()
    assert bootstrap_md.read_text(encoding="utf-8") == saved["context_text"]


def test_precompiler_scenarios_and_cache(tmp_path: Path):
    gen = _generator(tmp_path)
    query = gen.query
    metrics = gen.budget_predictor.metrics
    pre = Precompiler(gen, query, metrics, project_root=tmp_path)
    scenarios = pre.predict_next_session()
    assert scenarios
    assert abs(sum(s["probability"] for s in scenarios) - 1.0) < 0.02
    for s in scenarios:
        assert "description" in s
        assert "probability" in s

    ctx = pre.precompile(scenarios[0])
    assert ctx.get("context_text")
    cached = pre.get_cached_bootstrap(scenarios[0]["scenario_id"])
    assert cached is not None

    pre.record_prediction_outcome(scenarios[0]["scenario_id"], True)
    acc = pre.prediction_accuracy()
    assert acc["total"] >= 1

    warmed = pre.warm_up()
    assert warmed is not None


def test_tier1_in_generated_bootstrap(tmp_path: Path):
    gen = _generator(tmp_path)
    ctx = gen.preview_bootstrap()
    text = ctx["context_text"]
    assert "PHASE_01" in text
    assert "P1_T1" in text or "Active:" in text
    assert estimate_tokens(text) <= BOOTSTRAP_MAX_TOKENS + 200


def test_infer_session_type_debug():
    phase = {"phase_type": SessionType.BUILD.value}
    sub = {"name": "Fix login bug", "estimated_tokens": 4000}
    assert infer_session_type(sub, phase) == SessionType.DEBUG
