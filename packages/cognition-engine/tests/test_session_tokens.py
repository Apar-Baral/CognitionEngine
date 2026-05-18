"""Tests for session token normalization."""

from src.memory.session_tokens import session_tokens_consumed


def test_session_tokens_consumed_flat():
    assert session_tokens_consumed({"tokens_consumed": 42}) == 42


def test_session_tokens_consumed_nested():
    assert session_tokens_consumed({"tokens": {"total": 99}}) == 99


def test_session_tokens_consumed_missing():
    assert session_tokens_consumed({}) == 0
