#!/usr/bin/env python3
"""Dev helper: append sample session entries for dogfood tracker testing."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "packages" / "cognition-engine" / "src"))

from cognition_engine.service import CognitionService  # noqa: E402


def main() -> None:
    import os

    os.chdir(REPO)
    svc = CognitionService(REPO)
    if not svc.store.exists():
        svc.init_project(name="Cognition Engine", meta_tool=True)

    samples = [
        ("DNA schema and loader implemented", 8000, True),
        ("Session store and operational memory", 9500, True),
        ("Bootstrap compiler under 2k tokens", 11000, True),
        ("CLI ce init/start/end/status", 14000, True),
        ("Cursor and Claude Code adapters", 7500, True),
        ("Token budget tracker and ce budget", 6000, True),
        ("Truth index and import validator", 12000, True),
        ("Unit tests and dogfood docs", 5000, False),
        ("Documentation and monorepo layout", 3000, True),
        ("Dogfood gate: 10 sessions on CE repo", 2500, True),
    ]

    for i, (summary, tokens, complete) in enumerate(samples, 1):
        try:
            svc.start_session(budget=50_000)
        except Exception:
            pass
        svc.end_session(
            summary=summary,
            tokens=tokens,
            complete_sub_task=complete,
        )
        print(f"Session {i}: {summary}")

    print("\nRun: ce status")


if __name__ == "__main__":
    main()
