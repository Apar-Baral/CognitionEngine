"""Tests for setup wizard and git helpers."""

from __future__ import annotations

from pathlib import Path

from src.cli.git_helpers import auto_commit, is_git_repo, write_project_gitignore
from src.cli.setup_wizard import project_config_template
from src.core.config import Config


def test_project_config_template_has_git():
    assert project_config_template()["git"]["auto_commit"] is True


def test_write_gitignore(tmp_path: Path):
    write_project_gitignore(tmp_path, merge=False)
    assert (tmp_path / ".gitignore").is_file()
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".cognition/sessions/" in text


def test_auto_commit_no_repo(tmp_path: Path):
    assert auto_commit(tmp_path, "test") is None


def test_should_auto_commit(tmp_path: Path):
    cog = tmp_path / ".cognition"
    cog.mkdir()
    (cog / "config.yaml").write_text(
        "git:\n  auto_commit: true\n  auto_commit_message_prefix: 'ce:'\n",
        encoding="utf-8",
    )
    cfg = Config(tmp_path)
    from src.cli.git_helpers import should_auto_commit

    assert should_auto_commit(cfg) is True
