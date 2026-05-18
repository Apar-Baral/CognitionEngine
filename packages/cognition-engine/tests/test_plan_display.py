"""Plan display helpers."""

from __future__ import annotations

from src.planner.phase_generator import generate_goal_plan
from src.repl.plan_display import format_plan_markup


def test_format_plan_markup_contains_phases():
    phases = generate_goal_plan("Build an XSS scanner", num_phases=8)
    text = format_plan_markup(phases, goal="Build an XSS scanner", overall_completion=0.0)
    assert "MASTER PLAN" in text
    assert "PHASE_01" in text
    assert "Discovery" in text
