"""
Provider-specific HTTP request builder from unified internal format.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class RequestBuilder:
    """Build (url, headers, body) for any registered provider."""

    def build_request(
        self,
        unified: dict[str, Any],
        model: dict[str, Any],
        *,
        api_key: str = "",
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        provider = model.get("provider", "openai")
        if provider == "anthropic":
            url, headers, body = self._build_anthropic(unified, model, api_key)
        elif provider == "google":
            url, headers, body = self._build_google(unified, model, api_key)
        elif provider == "ollama":
            url, headers, body = self._build_ollama(unified, model)
        else:
            url, headers, body = self._build_openai(unified, model, api_key, provider)
        self._validate_limits(unified, model)
        logger.debug("Built %s request to %s", provider, url)
        return url, headers, body

    def build_headers(self, model: dict[str, Any], api_key: str = "") -> dict[str, str]:
        _, headers, _ = self.build_request(
            {"messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
            model,
            api_key=api_key,
        )
        return headers

    def validate_request(
        self, unified: dict[str, Any], model: dict[str, Any]
    ) -> list[str]:
        warnings: list[str] = []
        messages = unified.get("messages") or []
        if not messages and not unified.get("system_prompt"):
            warnings.append("No messages or system prompt in request")
        caps = model.get("capabilities") or []
        if unified.get("tools") and "tool_use" not in caps:
            warnings.append("Model does not support tool_use")
        est = self._estimate_tokens(unified)
        if est > int(model.get("max_context", 0)) * 0.95:
            warnings.append(f"Estimated {est} tokens may exceed max_context")
        if int(unified.get("max_tokens", 0)) > int(model.get("max_output", 0)):
            warnings.append("max_tokens exceeds model max_output; will be capped")
        return warnings

    def _build_anthropic(
        self, unified: dict[str, Any], model: dict[str, Any], api_key: str
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = model["api_base"].rstrip("/") + model["endpoint"]
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            model["auth_header"]: api_key,
        }
        body: dict[str, Any] = {
            "model": model["id"],
            "max_tokens": min(
                int(unified.get("max_tokens", 4096)),
                int(model.get("max_output", 4096)),
            ),
            "messages": self._anthropic_messages(unified),
        }
        if unified.get("system_prompt"):
            body["system"] = unified["system_prompt"]
        if unified.get("tools"):
            body["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
                }
                for t in unified["tools"]
            ]
        if unified.get("temperature") is not None:
            body["temperature"] = unified["temperature"]
        if unified.get("stream"):
            body["stream"] = True
        if "extended_thinking" in (model.get("capabilities") or []):
            body.setdefault("thinking", {"type": "enabled", "budget_tokens": 8000})
        return url, headers, body

    def _build_openai(
        self,
        unified: dict[str, Any],
        model: dict[str, Any],
        api_key: str,
        provider: str,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = model["api_base"].rstrip("/") + model["endpoint"]
        auth_val = f"{model.get('auth_prefix', '')}{api_key}".strip()
        headers = {"content-type": "application/json"}
        if model.get("auth_header"):
            headers[model["auth_header"]] = auth_val
        if provider == "openrouter":
            headers["HTTP-Referer"] = "https://cognition-engine.dev"
            headers["X-Title"] = "Cognition Engine"

        messages: list[dict[str, Any]] = []
        if unified.get("system_prompt"):
            messages.append({"role": "system", "content": unified["system_prompt"]})
        messages.extend(unified.get("messages") or [])

        body: dict[str, Any] = {
            "model": model["id"],
            "messages": messages,
            "max_tokens": min(
                int(unified.get("max_tokens", 4096)),
                int(model.get("max_output", 4096)),
            ),
        }
        if unified.get("tools"):
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("parameters", {"type": "object", "properties": {}}),
                    },
                }
                for t in unified["tools"]
            ]
        if unified.get("temperature") is not None:
            body["temperature"] = unified["temperature"]
        if unified.get("stream"):
            body["stream"] = True
        return url, headers, body

    def _build_google(
        self, unified: dict[str, Any], model: dict[str, Any], api_key: str
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        endpoint = model["endpoint"].replace("{model}", model["id"])
        url = f"{model['api_base'].rstrip('/')}{endpoint}?{urlencode({'key': api_key})}"
        headers = {"content-type": "application/json"}
        contents = []
        for msg in unified.get("messages") or []:
            role = "user" if msg.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg.get("content", "")}]})
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "maxOutputTokens": min(
                    int(unified.get("max_tokens", 4096)),
                    int(model.get("max_output", 4096)),
                ),
            },
        }
        if unified.get("system_prompt"):
            body["systemInstruction"] = {"parts": [{"text": unified["system_prompt"]}]}
        if unified.get("tools"):
            body["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": t["name"],
                            "description": t.get("description", ""),
                            "parameters": t.get("parameters", {}),
                        }
                        for t in unified["tools"]
                    ]
                }
            ]
        if unified.get("temperature") is not None:
            body["generationConfig"]["temperature"] = unified["temperature"]
        return url, headers, body

    def _build_ollama(
        self, unified: dict[str, Any], model: dict[str, Any]
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        url = model["api_base"].rstrip("/") + model["endpoint"]
        messages = []
        if unified.get("system_prompt"):
            messages.append({"role": "system", "content": unified["system_prompt"]})
        messages.extend(unified.get("messages") or [])
        body = {
            "model": model["id"],
            "messages": messages,
            "stream": bool(unified.get("stream")),
        }
        return url, {"content-type": "application/json"}, body

    def _anthropic_messages(self, unified: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        for msg in unified.get("messages") or []:
            role = msg.get("role", "user")
            if role == "system":
                continue
            if role == "tool":
                role = "user"
            out.append({"role": role, "content": msg.get("content", "")})
        return out

    def _estimate_tokens(self, unified: dict[str, Any]) -> int:
        text = json.dumps(unified, default=str)
        return len(text) // 4

    def _validate_limits(self, unified: dict[str, Any], model: dict[str, Any]) -> None:
        for w in self.validate_request(unified, model):
            logger.warning("Request validation: %s", w)
