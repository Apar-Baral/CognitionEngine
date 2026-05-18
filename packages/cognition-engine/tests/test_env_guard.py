"""Tests for environment guard."""

from __future__ import annotations

from src.core.env_guard import cognition_engine_home, env_warning_message, is_venv_active


def test_is_venv_active_bool():
    assert isinstance(is_venv_active(), bool)


def test_cognition_engine_home_path():
    home = cognition_engine_home()
    assert home.name == "CognitionEngine" or "CognitionEngine" in str(home)


def test_env_warning_in_venv_or_message():
    msg = env_warning_message()
    if is_venv_active():
        assert msg is None
    else:
        assert msg is None or "virtualenv" in msg.lower() or "install" in msg.lower()
