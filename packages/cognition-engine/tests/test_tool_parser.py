"""Tool JSON extraction from model replies."""

from __future__ import annotations

from src.agent.tool_parser import extract_tool_calls


def test_bare_json_tool():
    raw = '{"tool": "write_file", "args": {"path": "a.py", "content": "x"}}'
    calls = extract_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0]["tool"] == "write_file"


def test_fenced_json_tool():
    raw = 'Here:\n```json\n{"tool": "read_file", "args": {"path": "b.py"}}\n```\n'
    calls = extract_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0]["tool"] == "read_file"


def test_prose_plus_tool_json():
    raw = (
        "I will create the file now.\n"
        '{"tool": "write_file", "args": {"path": "c.py", "content": "ok"}}'
    )
    calls = extract_tool_calls(raw)
    assert len(calls) == 1


def test_no_tools_in_plain_text():
    assert extract_tool_calls("Just a normal answer with no JSON.") == []
