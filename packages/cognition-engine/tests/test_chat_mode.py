"""Quick vs agentic chat routing."""

from __future__ import annotations

from src.agent.chat_mode import is_agentic_request


def test_simple_question_is_quick():
    assert not is_agentic_request("What is XSS?")
    assert not is_agentic_request("hello")
    assert not is_agentic_request("explain typer in one paragraph")


def test_file_task_is_agentic():
    assert is_agentic_request("create 20 files with payloads in ./payloads")
    assert is_agentic_request("delete the file you made")
    assert is_agentic_request("run pytest and fix failures")
