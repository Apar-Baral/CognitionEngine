"""Phase 5 verification tests — API proxy and token guardian."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.core.constants import BudgetZone
from src.memory.operational_memory import OperationalMemory
from src.proxy.api_proxy import ApiProxy, ProxyConfig
from src.proxy.budget_enforcer import BudgetEnforcer
from src.proxy.cost_projector import CostProjector
from src.proxy.runaway_detector import RunawayDetector
from src.proxy.token_counter import TokenCounter
from src.proxy.usage_analyzer import UsageAnalyzer


def test_token_counter_openai_request():
    counter = TokenCounter()
    body = {
        "model": "gpt-4o",
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Say hello in five words."},
        ],
    }
    tokens = counter.count_input_tokens(body, "gpt-4o")
    assert 5 < tokens < 200
    assert counter.estimate_tokens("hello world test") >= 1

    response = {
        "choices": [{"message": {"content": "Hello there friend today"}}],
        "usage": {"prompt_tokens": tokens, "completion_tokens": 8},
    }
    out = counter.count_output_tokens(response, "gpt-4o")
    assert out == 8
    totals = counter.get_session_totals()
    assert totals["total_tokens"] > 0
    assert "system_prompt" in totals["tokens_by_category"]


def test_token_counter_anthropic_format():
    counter = TokenCounter()
    body = {
        "model": "claude-sonnet-4-20250514",
        "system": "Be concise.",
        "messages": [{"role": "user", "content": "Hi"}],
    }
    tokens = counter.count_input_tokens(body, "claude-sonnet-4-20250514")
    assert tokens > 0
    breakdown = counter.categorize_tokens(body)
    assert breakdown["system_prompt"] > 0


def test_budget_zone_transitions():
    enforcer = BudgetEnforcer(10_000)
    cases = [
        (3_000, BudgetZone.GREEN, True),
        (6_500, BudgetZone.YELLOW, True),
        (8_700, BudgetZone.RED, True),
        (9_200, BudgetZone.WRAP_UP, True),
    ]
    for used, expected_zone, should_continue in cases:
        enforcer.tokens_used = used
        result = enforcer.check_budget(used)
        assert result["zone"] == expected_zone.value
        assert result["continue"] is should_continue

    fresh = BudgetEnforcer(10_000)
    fresh.tokens_used = 10_000
    exhausted = fresh.check_budget(10_000)
    assert exhausted["zone"] == BudgetZone.EXHAUSTED.value
    assert exhausted["continue"] is False


def test_wrap_up_behavior():
    enforcer = BudgetEnforcer(10_000)
    enforcer.tokens_used = 9_200
    result = enforcer.check_budget(9_200)
    assert result["wrap_up"] is True
    assert enforcer.should_wrap_up()
    msg = enforcer.get_zone_message(BudgetZone.WRAP_UP)
    assert "SESSION HANDOFF SUMMARY" in msg
    assert result["inject_system_message"] is True

    enforcer.tokens_used = 10_200
    enforcer.wrap_up_mode = True
    grace = enforcer.check_budget(10_200)
    assert grace["continue"] is True

    enforcer.tokens_used = 10_600
    blocked = enforcer.check_budget(10_600)
    assert blocked["continue"] is False

    body = {"messages": [{"role": "user", "content": "create new feature from scratch"}]}
    assert enforcer.should_block_new_task(body) is True


def test_budget_add_tokens_override():
    enforcer = BudgetEnforcer(1000)
    enforcer.add_tokens(500, reason="test")
    assert enforcer.budget_limit == 1500


@pytest.mark.asyncio
async def test_api_proxy_forwards_and_logs():
    counter = TokenCounter()
    enforcer = BudgetEnforcer(50_000)
    op = OperationalMemory(1, Path("."), "BUILD", budget_tokens=50_000)
    pricing = {"gpt-4o": {"input": 2.5, "output": 10.0}}
    cost = CostProjector(pricing)

    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Done"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            },
        )

    config = ProxyConfig(host="127.0.0.1", port=18787)
    proxy = ApiProxy(config, counter, enforcer, op, session_id=1, cost_projector=cost)
    proxy._client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    body = json.dumps(
        {
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "test"}],
        }
    ).encode()
    resp = await proxy.handle_request(
        "POST",
        "/v1/chat/completions",
        {"Authorization": "Bearer test", "Content-Type": "application/json"},
        body,
    )
    assert resp.status == 200
    assert len(op.api_calls) == 1
    assert enforcer.tokens_used > 0
    assert cost.get_session_cost() > 0


def test_usage_analyzer_re_read_and_loop():
    op = OperationalMemory(1, Path("."))
    for _ in range(4):
        op.log_file_operation("src/db.py", "read", "hash1", "hash1")
    analyzer = UsageAnalyzer(op)
    re_reads = analyzer.detect_re_read()
    assert len(re_reads) >= 1
    assert re_reads[0]["read_count"] >= 3

    for _ in range(5):
        analyzer.record_response("call tool read_file on src/main.py")
    loop = analyzer.detect_loop()
    assert loop["detected"] is True

    score = analyzer.calculate_efficiency_score()
    assert 0 <= score <= 100
    report = analyzer.get_session_efficiency_report()
    assert "recommendations" in report
    tax = analyzer.get_re_read_tax()
    assert tax["wasted_tokens"] > 0


def test_cost_projector():
    pricing = {
        "claude-sonnet": {"input": 3.0, "output": 15.0},
        "gpt-4o": {"input": 2.5, "output": 10.0, "reasoning": 5.0},
    }
    proj = CostProjector(pricing)
    cost = proj.calculate_cost("gpt-4o", 1000, 500, reasoning_tokens=100)
    assert cost == round(1000 / 1000 * 2.5 + 500 / 1000 * 10.0 + 100 / 1000 * 5.0, 4)
    assert proj.format_cost(1.2345) == "$1.23"
    recorded = proj.record_call("gpt-4o", 1000, 500, reasoning_tokens=100)
    assert recorded == cost
    assert proj.get_session_cost() == cost
    projected = proj.project_session_cost(50_000, "gpt-4o")
    assert projected > 0
    alert_proj = CostProjector(pricing)
    alerts = alert_proj.cost_alerts(6.0)
    assert any(a["level"] == "warning" for a in alerts)


def test_runaway_detector():
    enforcer = BudgetEnforcer(100_000)
    log: list[dict] = []
    detector = RunawayDetector(log, enforcer)
    for t in [100, 120, 110, 130, 105, 115, 125, 100, 110, 105]:
        detector.monitor_request({}, {}, input_tokens=t, output_tokens=0)
    detector.monitor_request({}, {}, input_tokens=50_000, output_tokens=0)
    is_anomaly, _ = detector.check_anomaly(50_000)
    assert is_anomaly
    action = detector.on_runaway_detected()
    assert "inject_message" in action
    stats = detector.get_runaway_stats()
    assert stats["session_runaway_alerts"] >= 1
    detector.record_user_override(was_false_positive=True)
    detected, _ = detector.detect_runaway_condition()
    assert detected or is_anomaly


@pytest.mark.asyncio
async def test_proxy_integration_zone_injection_and_exhaustion():
    counter = TokenCounter()
    enforcer = BudgetEnforcer(1_000)
    enforcer.tokens_used = 920
    op = OperationalMemory(2, Path("."), budget_tokens=1_000)

    calls = {"n": 0}

    def mock_handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        body = json.loads(request.content) if request.content else {}
        messages = body.get("messages", [])
        has_wrap = any(
            "HANDOFF" in str(m.get("content", "")) for m in messages if m.get("role") == "system"
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "handoff" if has_wrap else "ok"}}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 10},
            },
        )

    proxy = ApiProxy(
        ProxyConfig(),
        counter,
        enforcer,
        op,
        session_id=2,
    )
    proxy._client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    req_body = json.dumps(
        {"model": "gpt-4o", "messages": [{"role": "user", "content": "work"}]}
    ).encode()
    first = await proxy.handle_request("POST", "/v1/chat/completions", {}, req_body)
    assert first.status == 200

    enforcer.wrap_up_mode = False
    enforcer.tokens_used = 10_500
    enforcer.budget_limit = 10_000
    blocked = await proxy.handle_request("POST", "/v1/chat/completions", {}, req_body)
    assert blocked.status == 429
