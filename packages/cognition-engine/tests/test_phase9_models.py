"""Phase 9 — dynamic model registry, routing, RL, and knowledge synthesis."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.core.constants import BudgetZone
from src.dna.loader import DNALoader
from src.dna.mutator import DNAMutator
from src.dna.query import DNAQuery
from src.memory.metrics_store import MetricsStore
from src.models.dynamic_registry import DynamicRegistry
from src.models.fallback_manager import FallbackManager
from src.models.intelligent_router import IntelligentRouter
from src.models.pricing_tracker import PricingTracker
from src.models.request_builder import RequestBuilder
from src.models.response_parser import ResponseParser
from src.optimizer.reward_calculator import RewardCalculator
from src.optimizer.rl_allocator import RLAllocator
from src.synthesizer.knowledge_synthesizer import KnowledgeSynthesizer
from src.synthesizer.trend_analyzer import TrendAnalyzer
from tests.dna_fixtures import minimal_valid_dna


@pytest.fixture
def models_yaml(tmp_path: Path) -> Path:
    path = tmp_path / "models.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "models": [
                    {
                        "id": "test-anthropic",
                        "provider": "anthropic",
                        "display_name": "Test Anthropic",
                        "api_base": "https://api.anthropic.com",
                        "endpoint": "/v1/messages",
                        "auth_header": "x-api-key",
                        "auth_prefix": "",
                        "capabilities": ["chat", "tool_use"],
                        "max_context": 100000,
                        "max_output": 4096,
                        "pricing": {"input_per_1k": 0.003, "output_per_1k": 0.015},
                        "tokenizer": "claude",
                        "default": True,
                        "tier": "premium",
                    },
                    {
                        "id": "test-openai",
                        "provider": "openai",
                        "display_name": "Test OpenAI",
                        "api_base": "https://api.openai.com",
                        "endpoint": "/v1/chat/completions",
                        "auth_header": "Authorization",
                        "auth_prefix": "Bearer ",
                        "capabilities": ["chat", "tool_use"],
                        "max_context": 128000,
                        "max_output": 8192,
                        "pricing": {"input_per_1k": 0.001, "output_per_1k": 0.002},
                        "tokenizer": "openai",
                        "default": True,
                        "tier": "economy",
                    },
                    {
                        "id": "test-deepseek",
                        "provider": "openai_compatible",
                        "display_name": "Test DeepSeek",
                        "api_base": "https://api.deepseek.com",
                        "endpoint": "/v1/chat/completions",
                        "auth_header": "Authorization",
                        "auth_prefix": "Bearer ",
                        "capabilities": ["chat"],
                        "max_context": 64000,
                        "max_output": 4096,
                        "pricing": {"input_per_1k": 0.0001, "output_per_1k": 0.0002},
                        "tokenizer": "openai_compatible",
                        "default": False,
                        "tier": "economy",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def registry(models_yaml: Path) -> DynamicRegistry:
    return DynamicRegistry(models_yaml)


def test_dynamic_registry_load_and_query(registry: DynamicRegistry):
    assert registry.load() == 3
    assert len(registry.list_models()) == 3
    m = registry.get_model("test-anthropic")
    assert m and m["provider"] == "anthropic"
    assert len(registry.list_by_provider("openai")) == 1
    assert len(registry.list_by_capability("tool_use")) == 2
    assert registry.get_default_model("economy")["id"] == "test-openai"


def test_request_builder_formats(registry: DynamicRegistry):
    builder = RequestBuilder()
    unified = {
        "system_prompt": "You are helpful.",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": 100,
        "temperature": 0.5,
    }
    anthropic = registry.get_model("test-anthropic")
    url, headers, body = builder.build_request(unified, anthropic, api_key="sk-test")
    assert "/messages" in url
    assert "x-api-key" in headers
    assert body["system"] == "You are helpful."

    openai = registry.get_model("test-openai")
    url2, headers2, body2 = builder.build_request(unified, openai, api_key="sk-test")
    assert "chat/completions" in url2
    assert headers2["Authorization"].startswith("Bearer")
    assert body2["messages"][0]["role"] == "system"

    ds = registry.get_model("test-deepseek")
    url3, _, body3 = builder.build_request(unified, ds, api_key="sk-test")
    assert "deepseek" in url3
    assert body3["model"] == "test-deepseek"


def test_response_parser_unified(registry: DynamicRegistry):
    parser = ResponseParser()
    anthropic_raw = {
        "content": [{"type": "text", "text": "Hello"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }
    out = parser.parse_response(anthropic_raw, registry.get_model("test-anthropic"), latency_ms=50)
    assert out["content"] == "Hello"
    assert out["usage"]["input_tokens"] == 10

    openai_raw = {
        "choices": [{"message": {"content": "Hi"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 8, "completion_tokens": 4},
        "model": "test-openai",
    }
    out2 = parser.parse_response(openai_raw, registry.get_model("test-openai"))
    assert out2["content"] == "Hi"
    assert out2["finish_reason"] == "stop"


def test_intelligent_router_tiers(registry: DynamicRegistry):
    fb = FallbackManager(registry, failure_threshold=3, initial_cooldown=0.01)
    router = IntelligentRouter(registry, fallback=fb)
    high = router.route_task(task_complexity="HIGH", budget_zone=BudgetZone.GREEN.value)
    assert high.tier == "premium"

    low_red = router.route_task(task_complexity="MEDIUM", budget_zone=BudgetZone.RED.value)
    assert low_red.tier == "economy"
    assert "economy" in low_red.explanation or low_red.tier == "economy"

    assert router.explain_routing(high)


def test_fallback_circuit_breaker(registry: DynamicRegistry):
    fb = FallbackManager(registry, failure_threshold=3, initial_cooldown=0.01)
    mid = "test-anthropic"
    assert fb.is_model_available(mid)
    for _ in range(3):
        fb.record_failure(mid)
    assert not fb.is_model_available(mid)
    fb.force_open_probe_ready(mid)
    fb.record_success(mid)
    assert fb.is_model_available(mid)


def test_pricing_tracker(registry: DynamicRegistry):
    pt = PricingTracker(registry)
    cost = pt.calculate_cost("test-openai", 1000, 500)
    expected = 1000 / 1000 * 0.001 + 500 / 1000 * 0.002
    assert abs(cost - expected) < 1e-6
    assert "$" in pt.format_cost(cost)


def test_rl_allocator(tmp_path: Path):
    cog = tmp_path / ".cognition"
    cog.mkdir()
    (cog / "dna.json").write_text(json.dumps(minimal_valid_dna()), encoding="utf-8")
    loader = DNALoader(tmp_path)
    query = DNAQuery(loader)
    mutator = DNAMutator(loader)
    metrics = MetricsStore(tmp_path, "test")
    rl = RLAllocator(query, metrics, mutator=mutator)
    alloc = rl.get_recommended_allocation("BUILD", "MEDIUM")
    assert alloc["explore_percent"] + alloc["implement_percent"] + alloc["verify_percent"] == 100
    rl.record_session_result("BUILD", "MEDIUM", alloc, 90.0, outcome={"efficiency_score": 90})
    stats = rl.get_learning_stats()
    assert stats["sessions_learned"] >= 1


def test_reward_calculator():
    rc = RewardCalculator()
    r = rc.calculate_reward(
        {
            "lines_accepted": 100,
            "tokens_consumed": 1000,
            "token_budget": 1200,
            "hallucination_rate": 0.01,
            "sub_task_completed": True,
        }
    )
    assert 0 <= r <= 100


def test_knowledge_synthesizer(tmp_path: Path):
    cog = tmp_path / ".cognition"
    cog.mkdir()
    (cog / "dna.json").write_text(json.dumps(minimal_valid_dna()), encoding="utf-8")
    loader = DNALoader(tmp_path)
    query = DNAQuery(loader)
    mutator = DNAMutator(loader)
    from src.memory.session_store import SessionStore

    store = SessionStore(tmp_path, "test")
    metrics = MetricsStore(tmp_path, "test")
    synth = KnowledgeSynthesizer(query, mutator, store, metrics)
    sessions = [
        {
            "session_id": i,
            "efficiency_score": 50 + i * 3,
            "tokens_consumed": 10000 + i * 500,
            "hallucinations_caught": i % 3,
            "started_at": f"2026-01-15T{10 + i:02d}:00:00+00:00",
        }
        for i in range(10)
    ]
    for s in sessions:
        store.write_event(s["session_id"], "metric", s)
    insights = synth.synthesize(
        {"session_id": 11, "efficiency_score": 80, "tokens_consumed": 12000, "hallucinations_caught": 1}
    )
    assert isinstance(insights, list)


def test_knowledge_synthesizer_operational_summary_shape(tmp_path: Path):
    """Regression: end-session summary uses tokens dict, not tokens_consumed."""
    cog = tmp_path / ".cognition"
    cog.mkdir()
    (cog / "dna.json").write_text(json.dumps(minimal_valid_dna()), encoding="utf-8")
    loader = DNALoader(tmp_path)
    query = DNAQuery(loader)
    mutator = DNAMutator(loader)
    from src.memory.session_store import SessionStore

    store = SessionStore(tmp_path, "test")
    metrics = MetricsStore(tmp_path, "test")
    synth = KnowledgeSynthesizer(query, mutator, store, metrics)
    summary = {
        "session_id": 1,
        "efficiency_score": 100.0,
        "hallucinations_caught": 0,
        "tokens": {"input": 0, "output": 0, "reasoning": 0, "total": 0},
    }
    insights = synth.synthesize(summary)
    assert isinstance(insights, list)


def test_reward_calculator_tokens_dict():
    rc = RewardCalculator()
    r = rc.calculate_reward(
        {
            "efficiency_score": 90,
            "tokens": {"total": 500},
            "budget_adherence_percentage": 100,
        }
    )
    assert 0 <= r <= 100


def test_trend_analyzer_increasing():
    ta = TrendAnalyzer()
    trend = ta.calculate_trend([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    assert trend["direction"] == "increasing"
    assert trend["pct_change"] > 0


def test_end_to_end_model_pipeline(registry: DynamicRegistry):
    builder = RequestBuilder()
    parser = ResponseParser()
    fb = FallbackManager(registry)
    router = IntelligentRouter(registry, fallback=fb)
    pricing = PricingTracker(registry)

    route = router.route_task(task_complexity="LOW", required_capabilities=["chat"])
    model = registry.get_model(route.model_id)
    unified = {"system_prompt": "Test", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 10}
    url, headers, body = builder.build_request(unified, model, api_key="key")
    assert url and headers and body

    raw = {
        "choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }
    parsed = parser.parse_response(raw, model)
    cost = pricing.calculate_cost(route.model_id, parsed["usage"]["input_tokens"], parsed["usage"]["output_tokens"])
    assert cost >= 0
    fb.record_success(route.model_id)
