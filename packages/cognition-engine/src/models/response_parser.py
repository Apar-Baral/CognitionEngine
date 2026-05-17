"""
Normalize provider responses into unified internal format.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class ResponseParser:
    """Parse provider-specific LLM responses."""

    def parse_response(
        self, raw: dict[str, Any], model: dict[str, Any], *, latency_ms: float = 0.0
    ) -> dict[str, Any]:
        provider = model.get("provider", "openai")
        if provider == "anthropic":
            return self._parse_anthropic(raw, model, latency_ms)
        if provider == "google":
            return self._parse_google(raw, model, latency_ms)
        return self._parse_openai(raw, model, latency_ms)

    def extract_usage(self, raw: dict[str, Any], model: dict[str, Any]) -> dict[str, int]:
        provider = model.get("provider", "openai")
        if provider == "anthropic":
            u = raw.get("usage") or {}
            return {
                "input_tokens": int(u.get("input_tokens", 0)),
                "output_tokens": int(u.get("output_tokens", 0)),
                "reasoning_tokens": 0,
            }
        if provider == "google":
            u = raw.get("usageMetadata") or {}
            return {
                "input_tokens": int(u.get("promptTokenCount", 0)),
                "output_tokens": int(u.get("candidatesTokenCount", 0)),
                "reasoning_tokens": 0,
            }
        u = raw.get("usage") or {}
        return {
            "input_tokens": int(u.get("prompt_tokens", u.get("input_tokens", 0))),
            "output_tokens": int(u.get("completion_tokens", u.get("output_tokens", 0))),
            "reasoning_tokens": int(u.get("reasoning_tokens", 0)),
        }

    def parse_error(self, raw: dict[str, Any], status_code: int = 0) -> dict[str, Any]:
        err = raw.get("error") or raw
        if isinstance(err, dict):
            message = err.get("message", str(err))
            err_type = err.get("type", "api_error")
        else:
            message = str(err)
            err_type = "api_error"
        retryable = status_code in (429, 500, 502, 503, 504)
        retry_after = None
        if status_code == 429:
            retry_after = float(raw.get("retry_after", 60))
        return {
            "error_type": err_type,
            "error_message": message,
            "retryable": retryable,
            "retry_after_seconds": retry_after,
        }

    def parse_streaming_chunk(
        self, chunk: str, model: dict[str, Any], accumulator: dict[str, Any]
    ) -> str | None:
        """Parse SSE chunk; return incremental text if any."""
        if not chunk.strip() or chunk.startswith(":"):
            return None
        data_line = chunk.strip()
        if data_line.startswith("data:"):
            data_line = data_line[5:].strip()
        if data_line in ("[DONE]", ""):
            return None
        try:
            payload = json.loads(data_line)
        except json.JSONDecodeError:
            return None
        provider = model.get("provider", "openai")
        if provider == "anthropic":
            if payload.get("type") == "content_block_delta":
                delta = payload.get("delta", {})
                text = delta.get("text", "")
                accumulator["content"] = accumulator.get("content", "") + text
                return text
        else:
            choices = payload.get("choices") or []
            if choices:
                delta = choices[0].get("delta", {})
                text = delta.get("content", "") or ""
                if text:
                    accumulator["content"] = accumulator.get("content", "") + text
                    return text
        return None

    def _parse_anthropic(
        self, raw: dict[str, Any], model: dict[str, Any], latency_ms: float
    ) -> dict[str, Any]:
        content_parts = []
        tool_calls = []
        for block in raw.get("content") or []:
            if block.get("type") == "text":
                content_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "arguments": block.get("input", {}),
                    }
                )
        return {
            "content": "".join(content_parts) or None,
            "tool_calls": tool_calls,
            "finish_reason": raw.get("stop_reason", "stop"),
            "usage": self.extract_usage(raw, model),
            "model": model["id"],
            "latency_ms": latency_ms,
        }

    def _parse_openai(
        self, raw: dict[str, Any], model: dict[str, Any], latency_ms: float
    ) -> dict[str, Any]:
        choices = raw.get("choices") or [{}]
        msg = choices[0].get("message") or {}
        tool_calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            args_raw = fn.get("arguments", "{}")
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except json.JSONDecodeError:
                args = {}
            tool_calls.append(
                {"id": tc.get("id", ""), "name": fn.get("name", ""), "arguments": args}
            )
        return {
            "content": msg.get("content"),
            "tool_calls": tool_calls,
            "finish_reason": choices[0].get("finish_reason", "stop"),
            "usage": self.extract_usage(raw, model),
            "model": raw.get("model", model["id"]),
            "latency_ms": latency_ms,
        }

    def _parse_google(
        self, raw: dict[str, Any], model: dict[str, Any], latency_ms: float
    ) -> dict[str, Any]:
        candidates = raw.get("candidates") or [{}]
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text_parts = []
        tool_calls = []
        for part in parts:
            if "text" in part:
                text_parts.append(part["text"])
            elif "functionCall" in part:
                fc = part["functionCall"]
                tool_calls.append(
                    {
                        "id": fc.get("name", ""),
                        "name": fc.get("name", ""),
                        "arguments": fc.get("args", {}),
                    }
                )
        return {
            "content": "".join(text_parts) or None,
            "tool_calls": tool_calls,
            "finish_reason": candidates[0].get("finishReason", "stop"),
            "usage": self.extract_usage(raw, model),
            "model": model["id"],
            "latency_ms": latency_ms,
        }
