from cognition_engine.bootstrap.context_compiler import compile_bootstrap_markdown, estimate_tokens, truncate_to_token_cap
from cognition_engine.core.constants import BOOTSTRAP_TOKEN_CAP


def test_bootstrap_under_cap():
    md = compile_bootstrap_markdown(
        project_name="test",
        strategic_lines=["[>] PHASE_01: Start"],
        tactical={
            "phase_id": "PHASE_01",
            "phase_name": "Start",
            "sub_task_id": "PHASE_01_T1",
            "sub_task_name": "Setup",
            "next_action": "Run ce init",
            "pending_sub_tasks": ["Setup"],
        },
        last_session=None,
        avoid_items=[],
    )
    assert estimate_tokens(md) <= BOOTSTRAP_TOKEN_CAP + 50


def test_truncate():
    long = "x" * 50000
    short = truncate_to_token_cap(long, cap=100)
    assert len(short) < len(long)
