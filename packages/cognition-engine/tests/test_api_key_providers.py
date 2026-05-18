"""API key bucket mapping for DeepSeek vs OpenAI."""

from src.cli.api_key_providers import (
    api_key_storage_provider,
    env_var_for_model,
    has_key_for_model,
)


def test_deepseek_model_uses_deepseek_bucket() -> None:
    assert api_key_storage_provider("deepseek-r4-pro") == "deepseek"
    assert env_var_for_model("deepseek-r4-pro") == "DEEPSEEK_API_KEY"


def test_has_key_deepseek_not_openai_slot() -> None:
    keys = {"deepseek": "sk-test"}
    assert has_key_for_model(keys, "deepseek-r4-pro")
    assert not has_key_for_model({}, "deepseek-r4-pro")
