"""REPL slash command tests."""

from __future__ import annotations

from pathlib import Path

from src.repl.repl_commands import is_chat_message, is_slash_command
from src.repl.session_bridge import SessionBridge
from tests.dna_fixtures import minimal_valid_dna
import json


def test_slash_detection():
    assert is_slash_command("/help")
    assert not is_slash_command("hello")
    assert is_chat_message("build the api")


def test_bridge_help(tmp_path: Path):
    cog = tmp_path / ".cognition"
    cog.mkdir()
    (cog / "dna.json").write_text(json.dumps(minimal_valid_dna()), encoding="utf-8")
    bridge = SessionBridge(tmp_path)
    out = bridge.dispatch("/help")
    assert "/model" in out
