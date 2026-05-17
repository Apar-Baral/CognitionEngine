"""
Token counting across LLM providers with categorization and session totals.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import tiktoken

logger = logging.getLogger(__name__)

FALLBACK_CHARS_PER_TOKEN = 4


class TokenCounter:
    """Count tokens for API requests and responses by provider/model."""

    def __init__(self) -> None:
        self._encodings: dict[str, tiktoken.Encoding] = {}
        self._session_input = 0
        self._session_output = 0
        self._api_call_count = 0
        self._tokens_by_category: dict[str, int] = {
            "system_prompt": 0,
            "user_message": 0,
            "assistant_message": 0,
            "tool_definitions": 0,
            "tool_call": 0,
            "tool_result": 0,
            "context": 0,
            "output": 0,
        }
        self._anthropic_ready = False
        try:
            import anthropic  # noqa: F401

            self._anthropic_ready = True
        except ImportError:
            logger.debug("anthropic SDK not installed; using tiktoken/fallback for Claude models")

    def count_input_tokens(self, request_body: dict[str, Any], model_id: str) -> int:
        breakdown = self.categorize_tokens(request_body)
        total = sum(breakdown.values())
        self._session_input += total
        self._api_call_count += 1
        for key, val in breakdown.items():
            if key in self._tokens_by_category:
                self._tokens_by_category[key] += val
        return total

    def count_output_tokens(self, response_body: dict[str, Any], model_id: str) -> int:
        usage = response_body.get("usage") or {}
        if usage.get("output_tokens") is not None:
            official = int(usage["output_tokens"])
        elif usage.get("completion_tokens") is not None:
            official = int(usage["completion_tokens"])
        else:
            official = None

        text_parts: list[str] = []
        if "content" in response_body:
            for block in response_body.get("content", []):
                if isinstance(block, dict) and block.get("type") == "text":
                    text_parts.append(block.get("text", ""))
        if "choices" in response_body:
            for choice in response_body.get("choices", []):
                msg = choice.get("message", {})
                content = msg.get("content", "")
                if isinstance(content, str):
                    text_parts.append(content)
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            text_parts.append(part.get("text", ""))
                for tc in msg.get("tool_calls", []) or []:
                    fn = tc.get("function", {})
                    text_parts.append(json.dumps(fn))

        counted = self._count_text("\n".join(text_parts), model_id)
        if official is not None:
            self.accuracy_validation(counted, official, model_id, "output")

        self._session_output += counted
        self._tokens_by_category["output"] += counted
        return official if official is not None else counted

    def count_messages(self, messages: list[dict[str, Any]], model_id: str) -> int:
        total = 0
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            text = _content_to_text(content)
            tokens = self._count_text(text, model_id)
            total += tokens
            cat = {
                "system": "system_prompt",
                "user": "user_message",
                "assistant": "assistant_message",
                "tool": "tool_result",
            }.get(role, "user_message")
            self._tokens_by_category[cat] += tokens

            for tc in msg.get("tool_calls", []) or []:
                fn = tc.get("function", {})
                t = self._count_text(json.dumps(fn), model_id)
                total += t
                self._tokens_by_category["tool_call"] += t
        return total

    def categorize_tokens(self, request_body: dict[str, Any]) -> dict[str, int]:
        model_id = request_body.get("model", "unknown")
        breakdown = {k: 0 for k in self._tokens_by_category if k != "output"}

        system = request_body.get("system")
        if system:
            breakdown["system_prompt"] = self._count_text(_system_to_text(system), model_id)

        for msg in request_body.get("messages", []):
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "user")
            text = _content_to_text(msg.get("content", ""))
            tokens = self._count_text(text, model_id)
            key = {
                "system": "system_prompt",
                "user": "user_message",
                "assistant": "assistant_message",
                "tool": "tool_result",
            }.get(role, "context")
            breakdown[key] += tokens

        tools = request_body.get("tools") or []
        for tool in tools:
            breakdown["tool_definitions"] += self._count_text(json.dumps(tool), model_id)

        return breakdown

    def estimate_tokens(self, text: str) -> int:
        """Fallback: chars/4, marked as estimate."""
        if not text:
            return 0
        return max(1, len(text) // FALLBACK_CHARS_PER_TOKEN)

    def get_session_totals(self) -> dict[str, Any]:
        return {
            "total_input_tokens": self._session_input,
            "total_output_tokens": self._session_output,
            "total_tokens": self._session_input + self._session_output,
            "tokens_by_category": dict(self._tokens_by_category),
            "api_calls_count": self._api_call_count,
        }

    def reset_session(self) -> None:
        self._session_input = 0
        self._session_output = 0
        self._api_call_count = 0
        for key in self._tokens_by_category:
            self._tokens_by_category[key] = 0

    def accuracy_validation(
        self,
        our_count: int,
        provider_count: int,
        model_id: str,
        direction: str,
    ) -> int:
        """Return provider count for billing; log if discrepancy > 5%."""
        if provider_count <= 0:
            return our_count
        diff = abs(our_count - provider_count) / provider_count
        if diff > 0.05:
            logger.warning(
                "Token count discrepancy %.1f%% for %s (%s): ours=%s provider=%s",
                diff * 100,
                model_id,
                direction,
                our_count,
                provider_count,
            )
        return provider_count

    def add_streaming_output(self, accumulated_text: str, model_id: str) -> int:
        """Count tokens from accumulated streaming response."""
        tokens = self._count_text(accumulated_text, model_id)
        self._session_output += tokens
        self._tokens_by_category["output"] += tokens
        return tokens

    def _count_text(self, text: str, model_id: str) -> int:
        if not text:
            return 0
        provider = _provider_for_model(model_id)
        if provider == "anthropic":
            return self._count_anthropic(text, model_id)
        if provider in ("openai", "deepseek", "openai_compatible"):
            return self._count_tiktoken(text, model_id)
        return self.estimate_tokens(text)

    def _count_anthropic(self, text: str, model_id: str) -> int:
        if self._anthropic_ready:
            try:
                import anthropic

                client = anthropic.Anthropic()
                if hasattr(client, "count_tokens"):
                    return int(client.count_tokens(text))  # type: ignore[no-any-return]
                if hasattr(anthropic, "Anthropic") and hasattr(
                    anthropic.Anthropic(), "messages"
                ):
                    # SDK count_tokens on messages API
                    pass
            except Exception:
                logger.debug("Anthropic count failed; using tiktoken fallback", exc_info=True)
        enc = self._get_encoding("cl100k_base")
        return len(enc.encode(text))

    def _count_tiktoken(self, text: str, model_id: str) -> int:
        enc_name = "cl100k_base"
        if "gpt-4" in model_id.lower():
            enc_name = "cl100k_base"
        elif "gpt-3.5" in model_id.lower():
            enc_name = "cl100k_base"
        enc = self._get_encoding(enc_name)
        return len(enc.encode(text))

    def _get_encoding(self, name: str) -> tiktoken.Encoding:
        if name not in self._encodings:
            self._encodings[name] = tiktoken.get_encoding(name)
        return self._encodings[name]


def _provider_for_model(model_id: str) -> str:
    mid = model_id.lower()
    if "claude" in mid or "anthropic" in mid:
        return "anthropic"
    if "deepseek" in mid:
        return "deepseek"
    if "gpt" in mid or "o1" in mid or "o3" in mid:
        return "openai"
    return "unknown"


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    parts.append(str(block.get("content", "")))
        return "\n".join(parts)
    return str(content) if content else ""


def _system_to_text(system: Any) -> str:
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "\n".join(
            b.get("text", "") for b in system if isinstance(b, dict) and b.get("type") == "text"
        )
    return str(system)
