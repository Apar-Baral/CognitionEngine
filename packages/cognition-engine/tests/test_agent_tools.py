"""Agent tool command allowlist."""

from __future__ import annotations

from src.agent.tools import command_is_allowed


def test_grep_pipeline_allowed():
    ok, _ = command_is_allowed("grep -r xss . | head -20")
    assert ok


def test_python_allowed():
    ok, _ = command_is_allowed("python3 -m pytest -q")
    assert ok


def test_rm_rf_blocked():
    ok, reason = command_is_allowed("rm -rf /")
    assert not ok
    assert "safety" in reason
