"""DSML tool markup from DeepSeek models."""

from __future__ import annotations

from src.agent.dsml_parser import extract_dsml_tool_calls, strip_dsml_markup
from src.agent.tool_parser import extract_tool_calls

DSML_SPACED = """
I'll list the project root.

< | | DSML | | tool_calls>
< | | DSML | | invoke name="list_dir">
< | | DSML | | parameter name="path" string="true">.</ | | DSML | | parameter>
< / | | DSML | | invoke>
< / | | DSML | | tool_calls>
"""

DSML_COMPACT = '''
I'll list files.
<|DSML|invoke name="list_dir">
<|DSML|parameter name="path" string="true">.</|DSML|parameter>
</|DSML|invoke>
'''


def test_strip_dsml_spaced():
    clean = strip_dsml_markup(DSML_SPACED)
    assert "dsml" not in clean.lower()
    assert "list the project" in clean


def test_extract_dsml_spaced():
    calls = extract_dsml_tool_calls(DSML_SPACED)
    assert len(calls) == 1
    assert calls[0]["tool"] == "list_dir"
    assert calls[0]["args"]["path"] == "."


def test_extract_dsml_compact():
    calls = extract_tool_calls(DSML_COMPACT)
    assert calls[0]["tool"] == "list_dir"
