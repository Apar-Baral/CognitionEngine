"""Model picker helpers."""

from __future__ import annotations

from src.cli.model_picker import (
    models_grouped_by_tier,
    resolve_model_id,
    select_options_for_widget,
)
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


def test_resolve_model_id_by_display_name():
    reg = DynamicRegistry(ensure_models_yaml())
    assert resolve_model_id("deepseek-r4-pro", reg) == "deepseek-r4-pro"
    assert resolve_model_id("DeepSeek R4 Pro", reg) == "deepseek-r4-pro"
    assert resolve_model_id("DEEPSEEK R4 PRO", reg) == "deepseek-r4-pro"


def test_resolve_model_id_invalid():
    reg = DynamicRegistry(ensure_models_yaml())
    assert resolve_model_id("not-a-real-model-xyz", reg) is None


def test_deepseek_r4_pro_api_model_name():
    reg = DynamicRegistry(ensure_models_yaml())
    model = reg.get_model("deepseek-r4-pro")
    assert model is not None
    assert DynamicRegistry.api_model_name(model) == "deepseek-v4-pro"
    from src.models.request_builder import RequestBuilder

    builder = RequestBuilder()
    unified = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 16}
    _, _, body = builder.build_request(unified, model, api_key="sk-test")
    assert body["model"] == "deepseek-v4-pro"
