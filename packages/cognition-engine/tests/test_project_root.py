"""Project root resolution — cwd wins over last_setup."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.cli.context import resolve_project_root


def test_resolve_prefers_cwd_over_last_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    other = tmp_path / "other-project"
    cwd_proj = tmp_path / "here"
    for p in (other, cwd_proj):
        p.mkdir()
        cog = p / ".cognition"
        cog.mkdir()
        (cog / "dna.json").write_text('{"schema_version":"1.0.0"}', encoding="utf-8")

    monkeypatch.chdir(cwd_proj)
    monkeypatch.setattr(
        "src.cli.setup_summary.load_last_setup",
        lambda: {"project_path": str(other)},
    )
    assert resolve_project_root() == cwd_proj.resolve()
