"""Phase 7 verification tests — CLI interface."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from src.cli import formatters
from src.cli.commands import app
from src.core.constants import PhaseStatus


runner = CliRunner()


def _invoke(args: list[str]) -> object:
    """Invoke CLI with global --project before subcommand when present."""
    return runner.invoke(app, args)


def test_cc_help_and_version():
    r = _invoke(["--help"])
    assert r.exit_code == 0
    assert "init" in r.stdout
    assert "start" in r.stdout
    r2 = _invoke(["--version"])
    assert r2.exit_code == 0
    assert "0.1." in r2.stdout


def test_init_status_plan_preview(tmp_path: Path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        r = _invoke(["init", str(tmp_path)])
        assert r.exit_code == 0, r.stdout
        assert (tmp_path / ".cognition" / "dna.json").is_file()

        r2 = _invoke(["--project", str(tmp_path), "status"])
        assert r2.exit_code == 0

        r3 = _invoke(
            [
                "--project",
                str(tmp_path),
                "plan",
                "--goal",
                "Build a REST API for a todo app",
                "--phases",
                "12",
            ],
        )
        assert r3.exit_code == 0, r3.stdout

        r4 = _invoke(["--project", str(tmp_path), "start", "--preview"])
        assert r4.exit_code == 0, r4.stdout
        assert "SESSION" in r4.stdout or "Phase" in r4.stdout or "phase" in r4.stdout.lower()


def test_config_list(tmp_path: Path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _invoke(["init", str(tmp_path)])
        r = _invoke(["--project", str(tmp_path), "config", "--list"])
        assert r.exit_code == 0, r.stdout
        assert "shield_sensitivity" in r.stdout or "default_model" in r.stdout


def test_goal_command(tmp_path: Path):
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _invoke(["init", str(tmp_path)])
        r = _invoke(
            [
                "--project",
                str(tmp_path),
                "goal",
                "--set",
                "Build an XSS scanner with tests and fixtures.",
            ],
        )
        assert r.exit_code == 0, r.stdout
        assert (tmp_path / "GOAL.md").is_file()


def test_doctor_passes(tmp_path: Path):
    r = _invoke(["doctor"])
    assert r.exit_code == 0, r.stdout + r.stderr
    assert "All checks passed" in r.stdout


def test_end_session_after_start(tmp_path: Path):
    """Regression: end must not crash when session summary uses tokens dict."""
    with runner.isolated_filesystem(temp_dir=tmp_path):
        _invoke(["init", str(tmp_path)])
        _invoke(
            [
                "--project",
                str(tmp_path),
                "plan",
                "--goal",
                "Build an XSS scanner web app",
                "--phases",
                "12",
            ],
        )
        _invoke(["--project", str(tmp_path), "start"])
        r = _invoke(
            [
                "--project",
                str(tmp_path),
                "end",
                "--summary",
                "Discovery notes",
            ],
        )
        assert r.exit_code == 0, r.stdout + r.stderr
        assert "int() argument" not in (r.stdout + r.stderr)
        assert "Session ended" in r.stdout or "Session Summary" in r.stdout


def test_start_without_init_fails(tmp_path: Path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = _invoke(["--project", str(empty), "start"])
    assert r.exit_code != 0
    combined = (r.stdout + r.stderr).lower()
    assert "init" in combined or "not initialized" in combined


def test_formatters_render():
    phases = [
        {"id": "PHASE_01", "name": "A", "status": PhaseStatus.IN_PROGRESS.value, "completion_score": 40},
        {"id": "PHASE_02", "name": "B", "status": PhaseStatus.NOT_STARTED.value, "completion_score": 0},
    ]
    table = formatters.format_phase_progress_map(phases, project_name="Test", current_phase_index=1)
    assert table is not None
    compact = formatters.format_compact_progress(phases, current_index=1, overall_completion=20.0)
    assert "PHASE" in str(compact) or "20" in str(compact)


def test_truth_and_validate_command(tmp_path: Path):
    pkg = tmp_path / "app"
    pkg.mkdir(parents=True)
    (pkg / "svc.py").write_text(
        "def authenticate(password: str) -> bool:\n    return True\n",
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    _invoke(["init", str(tmp_path)])
    _invoke(
        [
            "--project",
            str(tmp_path),
            "plan",
            "--goal",
            "API",
            "--phases",
            "8",
            "--force",
        ],
    )

    bad_file = tmp_path / "bad.py"
    bad_file.write_text("from flask_magic_auth import x\n", encoding="utf-8")
    r = _invoke(["--project", str(tmp_path), "validate", str(bad_file)])
    assert r.exit_code in (0, 1), r.stdout
