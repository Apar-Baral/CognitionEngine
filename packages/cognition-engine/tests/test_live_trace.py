"""Live agent trace formatting."""

from __future__ import annotations

from src.agent.live_trace import describe_tool_call
from src.repl.live_thinking import LiveAgentView, live_thinking_markup


def test_describe_write():
    s = describe_tool_call(
        {"tool": "write_file", "args": {"path": "a.py", "content": "hello"}}
    )
    assert "WRITE a.py" in s
    assert "5 bytes" in s


def test_live_panel_includes_stream():
    view = LiveAgentView(
        step=2,
        max_steps=40,
        status="Streaming…",
        stream='{"tool": "read',
        planned=["READ foo.py"],
        trace=["Model step 2/40"],
    )
    _, body = live_thinking_markup(0, view)
    assert "READ foo.py" in body
    assert "read" in body
