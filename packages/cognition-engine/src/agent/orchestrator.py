"""LLM agent loop for REPL chat."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from src.agent.context_assembler import ContextAssembler
from src.agent.tools import ToolRunner
from src.cli.context import ProjectContext
from src.models.dynamic_registry import DynamicRegistry
from src.models.request_builder import RequestBuilder
from src.models.response_parser import ResponseParser

logger = logging.getLogger(__name__)

TOOL_SPEC = """
You may request tools by replying with JSON only:
{"tool": "read_file", "args": {"path": "docs/discovery.md"}}
{"tool": "write_file", "args": {"path": "file.py", "content": "..."}}
{"tool": "run_command", "args": {"cmd": "grep -r pattern . | head"}}
Pipelines allowed. Commands include: python, pytest, git, grep, cat, find, ls, curl, npm, etc.
{"tool": "suggest_next", "args": {}}
Otherwise reply with normal markdown for the user.
"""


class AgentOrchestrator:
    def __init__(
        self,
        ctx: ProjectContext,
        *,
        on_activity: Callable[[str], None] | None = None,
    ) -> None:
        self.ctx = ctx
        self.assembler = ContextAssembler(ctx)
        self.tools = ToolRunner(ctx.root)
        self.builder = RequestBuilder()
        self.parser = ResponseParser()
        self._history: list[dict[str, str]] = []
        self._on_activity = on_activity or (lambda _msg: None)

    def _activity(self, msg: str) -> None:
        try:
            self._on_activity(msg)
        except Exception:
            logger.debug("activity callback failed", exc_info=True)

    @staticmethod
    def resolve_api_key(config: Any, provider: str) -> str | None:
        """Map model provider to configured API key."""
        key = config.get_api_key(provider)
        if key:
            return key
        if provider == "openai_compatible":
            for alt in ("deepseek", "openai"):
                key = config.get_api_key(alt)
                if key:
                    return key
        if provider == "openrouter":
            for alt in ("openrouter", "openai"):
                key = config.get_api_key(alt)
                if key:
                    return key
        if provider == "google":
            key = config.get_api_key("google")
            if key:
                return key
        for alt in ("anthropic", "openai", "deepseek", "google"):
            key = config.get_api_key(alt)
            if key:
                return key
        return None

    def _resolve_model(self) -> tuple[dict[str, Any], str]:
        model_id = str(self.ctx.config.get("default_model", "gpt-4o-mini"))
        reg = self.ctx.model_registry()
        model = reg.get_model(model_id)
        if not model:
            model = reg.get_default_model() or {}
            model_id = str(model.get("id", model_id))
        provider = str(model.get("provider", "openai"))
        key = self.resolve_api_key(self.ctx.config, provider)
        if not key:
            raise RuntimeError(
                f"No API key for provider '{provider}' (model: {model_id}). "
                "Run: cognition-engine setup --project .  or add keys to ~/.cognition/config.yaml"
            )
        return model, key

    def chat(self, user_message: str) -> str:
        self._history.append({"role": "user", "content": user_message})
        self._activity("Loading project context and session memory…")
        model, api_key = self._resolve_model()
        model_id = str(model.get("id", self.ctx.config.get("default_model", "?")))
        display = model.get("display_name") or model_id
        self._activity(f"Calling {display} ({DynamicRegistry.api_model_name(model)})…")
        system = self.assembler.build_system_prompt() + "\n" + TOOL_SPEC
        messages = [{"role": "user", "content": m["content"]} for m in self._history[-12:]]
        unified: dict[str, Any] = {
            "system_prompt": system,
            "messages": messages,
            "max_tokens": 4096,
            "temperature": 0.3,
        }
        url, headers, body = self.builder.build_request(unified, model, api_key=api_key)
        t0 = time.perf_counter()
        self._activity("Waiting for model response…")
        with httpx.Client(timeout=120.0) as client:
            resp = client.post(url, headers=headers, json=body)
            raw = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                err = self.parser.parse_error(raw, resp.status_code)
                raise RuntimeError(err.get("message", str(raw)))
        latency = (time.perf_counter() - t0) * 1000
        self._activity(f"Response received ({latency:.0f} ms) — parsing…")
        parsed = self.parser.parse_response(raw, model, latency_ms=latency)
        text = parsed.get("content", "") or ""
        usage = self.parser.extract_usage(raw, model)
        self._log_tokens(usage)

        tool_result = self._try_tool(text)
        if tool_result is not None:
            self._history.append({"role": "assistant", "content": tool_result})
            return tool_result

        self._history.append({"role": "assistant", "content": text})
        self._activity("Done.")
        return text

    def _try_tool(self, text: str) -> str | None:
        text = text.strip()
        if not text.startswith("{"):
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict) or "tool" not in data:
            return None
        name = data["tool"]
        args = data.get("args") or {}
        self._activity(f"Running tool: {name}…")
        if name == "read_file":
            return self.tools.read_file(str(args.get("path", "")))
        if name == "write_file":
            self._activity("Shield: validating Python before write…")
            return self.tools.write_file(
                str(args.get("path", "")),
                str(args.get("content", "")),
                self.ctx,
            )
        if name == "run_command":
            return self.tools.run_command(str(args.get("cmd", "")))
        if name == "suggest_next":
            self._activity("Computing next-step recommendations…")
            return self.tools.suggest_next(self.ctx)
        return f"Unknown tool: {name}"

    def _log_tokens(self, usage: dict[str, int]) -> None:
        state = self.ctx.load_session_state()
        if not state:
            return
        try:
            op = self.ctx.active_operational_memory()
            op.log_api_call(
                str(self.ctx.config.get("default_model", "agent")),
                "chat",
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
            )
        except Exception:
            logger.debug("Could not log tokens to operational memory", exc_info=True)
