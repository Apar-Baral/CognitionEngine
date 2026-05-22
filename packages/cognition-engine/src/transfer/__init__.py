"""Cross-project learning (features 42-45)."""

from src.transfer.registry import (
    extract_patterns,
    find_similar_projects,
    register_project,
    suggest_plan_bootstrap,
)

__all__ = [
    "register_project",
    "extract_patterns",
    "find_similar_projects",
    "suggest_plan_bootstrap",
]
