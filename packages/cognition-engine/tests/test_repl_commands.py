"""REPL slash command tests."""

from __future__ import annotations

import json
from pathlib import Path

from src.repl.repl_commands import is_chat_message, is_slash_command
from src.repl.session_bridge import SessionBridge
from tests.dna_fixtures import minimal_valid_dna


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


def test_plan_updates_goal_file(tmp_path: Path):
    cog = tmp_path / ".cognition"
    cog.mkdir()
    (cog / "dna.json").write_text(json.dumps(minimal_valid_dna()), encoding="utf-8")
    old_goal = "old stale goal"
    (tmp_path / "GOAL.md").write_text(old_goal, encoding="utf-8")

    bridge = SessionBridge(tmp_path)
    new_goal = "build a CLI based XSS bug bounty automation tool"
    out = bridge.dispatch(f"/plan {new_goal}")

    assert "MASTER PLAN" in out
    assert new_goal in bridge.ctx.get_project_goal()
    assert new_goal in (tmp_path / "GOAL.md").read_text(encoding="utf-8")
    assert old_goal not in (tmp_path / "GOAL.md").read_text(encoding="utf-8")
