"""Agent permission classification and grants."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.permissions import (
    PERM_DELETE,
    grants_from_session_state,
    merge_grants_into_session,
    permission_for_command,
    permission_for_tool,
)
from src.agent.permission_gate import SessionPermissionGate
from src.agent.permissions import PermissionDecision
from src.agent.tools import ToolRunner, command_is_allowed


def test_delete_file_tool_needs_delete_permission():
    cat, detail = permission_for_tool("delete_file", {"path": "foo.py"})
    assert cat == PERM_DELETE
    assert "foo.py" in detail


def test_rm_command_needs_delete_permission():
    cat, _ = permission_for_command("rm payloads/test.py")
    assert cat == PERM_DELETE


def test_rm_rf_blocked_even_with_grant():
    ok, reason = command_is_allowed("rm -rf .", grants=frozenset({PERM_DELETE}))
    assert not ok
    assert "blocked" in reason.lower()


def test_rm_allowed_with_session_grant():
    ok, _ = command_is_allowed("rm foo.txt", grants=frozenset({PERM_DELETE}))
    assert ok


def test_rm_denied_without_grant():
    ok, reason = command_is_allowed("rm foo.txt")
    assert not ok
    assert "allowlist" in reason or "delete" in reason.lower()


def test_session_grants_roundtrip():
    state = merge_grants_into_session({"session_id": 1}, {PERM_DELETE})
    assert grants_from_session_state(state) == {PERM_DELETE}


def test_permission_gate_remembers_session(tmp_path: Path):
  class Ctx:
    def __init__(self) -> None:
      self._state: dict | None = None

    def load_session_state(self):
      return self._state

    def save_session_state(self, data: dict) -> None:
      self._state = data

  ctx = Ctx()
  calls: list[tuple[str, str]] = []

  def ask(cat: str, detail: str) -> PermissionDecision:
    calls.append((cat, detail))
    return PermissionDecision(True, remember_session=True)

  gate = SessionPermissionGate(ctx, on_request=ask)
  assert gate.ensure(PERM_DELETE, "delete x")
  assert gate.ensure(PERM_DELETE, "delete y")
  assert len(calls) == 1
  assert PERM_DELETE in grants_from_session_state(ctx.load_session_state())


def test_delete_file_tool(tmp_path: Path):
    f = tmp_path / "gone.txt"
    f.write_text("x", encoding="utf-8")
    runner = ToolRunner(tmp_path)
    assert runner.delete_file("gone.txt").startswith("Deleted")
    assert not f.exists()
