"""Phase 4 verification tests — session bootstrap system."""

from __future__ import annotations

from pathlib import Path

from src.bootstrap.avoid_register import AvoidRegister
from src.bootstrap.bootstrap_generator import BootstrapGenerator, infer_session_type
from src.bootstrap.budget_predictor import BudgetPredictor
from src.bootstrap.context_compiler import ContextCompiler, estimate_tokens
from src.core.constants import BOOTSTRAP_MAX_TOKENS, SessionType
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


def test_estimate_tokens():
    assert estimate_tokens("one two three four") >= 4


def test_context_compiler_within_budget(tmp_path: Path):
    query, _, strategic, _, _ = _setup(tmp_path)
    tactical = TacticalMemory(query, "PHASE_01")
    compiler = ContextCompiler(strategic, tactical, project_root=tmp_path)
    text = compiler.compile_context("Implement bootstrap", BOOTSTRAP_MAX_TOKENS)
    assert "SESSION BOOTSTRAP" in text
    assert "PHASE_01" in text
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


def test_bootstrap_generator_end_to_end(tmp_path: Path):
    query, mutator, strategic, sessions, metrics = _setup(tmp_path)
    tactical = TacticalMemory(query, "PHASE_01", mutator)
    avoid = AvoidRegister(query, mutator)
    compiler = ContextCompiler(strategic, tactical, project_root=tmp_path)
    predictor = BudgetPredictor(metrics, query)
    gen = BootstrapGenerator(
        strategic,
        tactical,
        compiler,
        avoid,
        predictor,
        query,
        session_store=sessions,
        project_root=tmp_path,
    )
    ctx = gen.generate("Continue phase 1 task 1")
    assert ctx["context_text"]
    assert ctx["phase_id"] == "PHASE_01"
    assert ctx["token_count"] <= BOOTSTRAP_MAX_TOKENS + 150
    assert ctx["recommended_budget"] >= ctx.get("predicted_tokens", 0)


def test_infer_session_type_debug():
    phase = {"phase_type": SessionType.BUILD.value}
    sub = {"name": "Fix login bug", "estimated_tokens": 4000}
    assert infer_session_type(sub, phase) == SessionType.DEBUG
