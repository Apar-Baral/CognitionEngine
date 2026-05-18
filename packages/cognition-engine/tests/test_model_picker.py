"""Model picker helpers."""

from __future__ import annotations

from src.cli.model_picker import models_grouped_by_tier, select_options_for_widget
from src.models.dynamic_registry import DynamicRegistry, ensure_models_yaml


def test_select_options_non_empty():
    reg = DynamicRegistry(ensure_models_yaml())
    opts = select_options_for_widget(reg)
    assert len(opts) >= 1
    assert isinstance(opts[0], tuple)
    assert len(opts[0]) == 2


def test_models_grouped_filter():
    reg = DynamicRegistry(ensure_models_yaml())
    groups = models_grouped_by_tier(reg, query="claude")
    assert isinstance(groups, list)
