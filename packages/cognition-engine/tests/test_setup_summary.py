"""Tests for setup summary persistence."""

from __future__ import annotations

from pathlib import Path

from src.cli.setup_summary import (
    format_setup_summary_rich,
    load_project_setup_summary,
    save_last_setup,
    save_project_setup_summary,
)


def test_save_and_format_setup_summary(tmp_path: Path, monkeypatch):
    import src.cli.setup_summary as mod

    fake_global = tmp_path / "last_setup.yaml"
    monkeypatch.setattr(mod, "LAST_SETUP_GLOBAL", str(fake_global))
    save_last_setup({"default_model": "gpt-4o-mini", "install_type": "slim"})
    text = format_setup_summary_rich({"default_model": "gpt-4o-mini", "install_type": "slim"}, {})
    assert "gpt-4o-mini" in text
    assert "slim" in text


def test_project_setup_summary(tmp_path: Path):
    cog = tmp_path / ".cognition"
    cog.mkdir()
    save_project_setup_summary(
        tmp_path,
        {"default_model": "claude-sonnet", "github_push": "declined", "git_initialized": True},
    )
    loaded = load_project_setup_summary(tmp_path)
    assert loaded["github_push"] == "declined"
    assert loaded["git_initialized"] is True
