"""CE platform identity in prompts."""

from __future__ import annotations

from src.agent.ce_identity import ce_platform_identity


def test_identity_lists_core_features():
    text = ce_platform_identity()
    assert "Hallucination Shield" in text
    assert "Reinforcement learning" in text
    assert "Memory" in text
    assert "Planner" in text or "plan" in text.lower()
    assert "Never say" in text or "never say" in text.lower()
