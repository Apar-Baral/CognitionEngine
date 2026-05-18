"""LLM agent loop for REPL chat — multi-step tool execution (agentic)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from src.agent.context_assembler import ContextAssembler
from src.agent.tool_parser import extract_tool_calls
from src.agent.tools import ToolRunner
from src.cli.context import ProjectContext
from src.models.dynamic_registry import DynamicRegistry
from src.models.request_builder import RequestBuilder
from src.models.response_parser import ResponseParser

logger = logging.getLogger(__name__)

MAX_AGENT_STEPS = 40

TOOL_SPEC = """
## Tools (you MUST use these to change the project — not chat-only plans)

Reply with one JSON object per action (no markdown prose instead of tools):

{"tool": "write_file", "args": {"path": "relative/path.py", "content": "full file text"}}
{"tool": "read_file", "args": {"path": "relative/path.py"}}
{"tool": "list_dir", "args": {"path": "."}}
{"tool": "run_command", "args": {"cmd": "python script.py"}}
{"tool": "suggest_next", "args": {}}

Rules:
- Creating N files = N separate write_file calls (one path each, full content each).
- To run scripts or shell: run_command (python, bash, grep, find, mkdir, etc.).
- After each tool you receive [tool result] and may call more tools in the next step.
- When the task is fully done, reply with normal markdown only (no tool JSON).
- NEVER claim files were created without calling write_file.
"""


class AgentOrchestrator:
    def __init__(
        self,
        ctx: ProjectContext,
        *,
        on_activity: Callable[[str], None] | None = None,
        on_tokens: Callable[[dict[str, int]], None] | None = None,
    ) -> None:
        self.ctx = ctx
        self.assembler = ContextAssembler(ctx)
        self.tools = ToolRunner(ctx.root)
        self.builder = RequestBuilder()
        self.parser = ResponseParser()
        self._history: list[dict[str, str]] = []
        self._on_activity = on_activity or (lambda _msg: None)
        self._on_tokens = on_tokens or (lambda _u: None)
        self.session_tokens: dict[str, int] = {
            "input": 0,
            "output": 0,
            "total": 0,
            "last_turn": 0,
        }
        self._files_written_this_turn = 0
        self._commands_run_this_turn = 0

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
            from src.cli.api_key_providers import api_key_storage_provider

            model_id = str(config.get("default_model", ""))
            preferred = api_key_storage_provider(model_id)
            seen: set[str] = set()
            for alt in (preferred, "deepseek", "openai", "openai_compatible"):
                if alt in seen:
                    continue
                seen.add(alt)
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
        self._files_written_this_turn = 0
        self._commands_run_this_turn = 0
        self._activity("Agentic mode — will run tools until task is done or step limit")
        model, api_key = self._resolve_model()
        system = self.assembler.build_system_prompt() + "\n" + TOOL_SPEC
        last_natural = ""

        for step in range(1, MAX_AGENT_STEPS + 1):
            self._activity(f"Model step {step}/{MAX_AGENT_STEPS}…")
            text = self._call_model(model, api_key, system)
            calls = extract_tool_calls(text)
            if not calls:
                last_natural = text.strip()
                if last_natural:
                    self._activity("Agent finished — final response ready")
                    self._history.append({"role": "assistant", "content": last_natural})
                    summary = self._turn_summary()
                    if summary and self._files_written_this_turn:
                        return f"{summary}\n\n{last_natural}"
                    return last_natural
                self._activity("Empty model reply — stopping")
                break

            self._history.append({"role": "assistant", "content": text})
            tool_results: list[str] = []
            for call in calls:
                result = self._execute_tool(call)
                tool_results.append(result)
                preview = result.replace("\n", " ")[:160]
                self._activity(f"✓ Done: {preview}")

            combined = "\n\n".join(tool_results)
            self._history.append(
                {
                    "role": "user",
                    "content": f"[tool results — continue until task complete]\n{combined}",
                }
            )

        summary = self._turn_summary()
        msg = (
            f"Stopped after {MAX_AGENT_STEPS} agent steps. "
            f"{summary or 'Use trace panel for details.'}"
        )
        if last_natural:
            msg = f"{summary}\n\n{last_natural}\n\n{msg}" if summary else f"{last_natural}\n\n{msg}"
        self._history.append({"role": "assistant", "content": msg})
        return msg

    def _turn_summary(self) -> str:
        parts: list[str] = []
        if self._files_written_this_turn:
            parts.append(f"**Files written this turn:** {self._files_written_this_turn}")
        if self._commands_run_this_turn:
            parts.append(f"**Commands run:** {self._commands_run_this_turn}")
        return " · ".join(parts)

    def _call_model(self, model: dict[str, Any], api_key: str, system: str) -> str:
        model_id = str(model.get("id", self.ctx.config.get("default_model", "?")))
        display = model.get("display_name") or model_id
        self._activity(f"Calling {display} ({DynamicRegistry.api_model_name(model)})…")
        messages = [{"role": m["role"], "content": m["content"]} for m in self._history[-16:]]
        unified: dict[str, Any] = {
            "system_prompt": system,
            "messages": messages,
            "max_tokens": 8192,
            "temperature": 0.2,
        }
        url, headers, body = self.builder.build_request(unified, model, api_key=api_key)
        t0 = time.perf_counter()
        self._activity("Waiting for model response…")
        with httpx.Client(timeout=180.0) as client:
            resp = client.post(url, headers=headers, json=body)
            raw = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                err = self.parser.parse_error(raw, resp.status_code)
                raise RuntimeError(err.get("message", str(raw)))
        latency = (time.perf_counter() - t0) * 1000
        self._activity(f"Response received ({latency:.0f} ms)")
        parsed = self.parser.parse_response(raw, model, latency_ms=latency)
        text = parsed.get("content", "") or ""
        usage = self.parser.extract_usage(raw, model)
        self._log_tokens(usage)
        inp = int(usage.get("input_tokens", 0))
        out = int(usage.get("output_tokens", 0))
        if inp or out:
            self._activity(f"Tokens this call: ↑{inp:,} in · ↓{out:,} out · Σ{inp + out:,}")
        return text

    def _execute_tool(self, data: dict[str, Any]) -> str:
        name = str(data.get("tool", ""))
        args = data.get("args") or {}
        if not isinstance(args, dict):
            args = {}

        if name == "read_file":
            path = str(args.get("path", ""))
            self._activity(f"📖 Reading file: {path}")
            return self.tools.read_file(path)

        if name == "list_dir":
            path = str(args.get("path", ".") or ".")
            self._activity(f"📂 Listing directory: {path}")
            return self.tools.list_dir(path)

        if name == "write_file":
            path = str(args.get("path", ""))
            content = str(args.get("content", ""))
            lines = content.count("\n") + 1 if content else 0
            self._activity(
                f"✏️ Writing file: {path} ({len(content)} bytes, ~{lines} lines)"
            )
            self._activity("🛡 Shield: validating before write…")
            result = self.tools.write_file(path, content, self.ctx)
            if result.startswith("Wrote"):
                self._files_written_this_turn += 1
            self._activity(f"📝 Write result: {result[:120]}")
            return result

        if name == "run_command":
            cmd = str(args.get("cmd", ""))
            preview = cmd if len(cmd) <= 100 else cmd[:97] + "…"
            self._activity(f"⚡ Running command: {preview}")
            result = self.tools.run_command(cmd)
            self._commands_run_this_turn += 1
            exit_hint = result[:80].replace("\n", " ")
            self._activity(f"⚡ Command output: {exit_hint}")
            return result

        if name == "suggest_next":
            self._activity("💡 Computing next-step recommendations…")
            return self.tools.suggest_next(self.ctx)

        self._activity(f"Unknown tool: {name}")
        return f"Unknown tool: {name}"

    def _emit_tokens(self, usage: dict[str, int]) -> None:
        inp = int(usage.get("input_tokens", 0))
        out = int(usage.get("output_tokens", 0))
        turn = inp + out
        self.session_tokens["input"] += inp
        self.session_tokens["output"] += out
        self.session_tokens["total"] += turn
        self.session_tokens["last_turn"] = turn
        try:
            self._on_tokens(
                {
                    "input_tokens": inp,
                    "output_tokens": out,
                    "turn_total": turn,
                    **self.session_tokens,
                }
            )
        except Exception:
            logger.debug("token callback failed", exc_info=True)

    def _log_tokens(self, usage: dict[str, int]) -> None:
        self._emit_tokens(usage)
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
