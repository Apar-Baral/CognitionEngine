"""LLM agent loop for REPL chat — multi-step tool execution (agentic)."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from src.agent.chat_mode import is_agentic_request
from src.agent.context_assembler import ContextAssembler
from src.agent.live_trace import describe_tool_call
from src.agent.permission_gate import PermissionCallback, SessionPermissionGate
from src.agent.permissions import permission_for_command, permission_for_tool
from src.agent.tool_parser import extract_tool_calls
from src.agent.tools import ToolRunner
from src.cli.context import ProjectContext
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
{"tool": "delete_file", "args": {"path": "relative/path.py"}}
{"tool": "run_command", "args": {"cmd": "python script.py"}}
{"tool": "suggest_next", "args": {}}

Rules:
- To delete a file: use delete_file (user must approve; session approval is remembered).
- Do not use rm in run_command unless the user has granted delete for this session.
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
        on_permission: PermissionCallback | None = None,
        on_stream: Callable[[str], None] | None = None,
    ) -> None:
        self.ctx = ctx
        self.assembler = ContextAssembler(ctx)
        self.tools = ToolRunner(ctx.root)
        self.builder = RequestBuilder()
        self.parser = ResponseParser()
        self._history: list[dict[str, str]] = []
        self._on_activity = on_activity or (lambda _msg: None)
        self._on_tokens = on_tokens or (lambda _u: None)
        self._permissions = SessionPermissionGate(
            ctx,
            on_request=on_permission,
            on_activity=self._activity,
        )
        self._on_stream = on_stream or (lambda _chunk: None)
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
        if is_agentic_request(user_message):
            return self._chat_agentic(user_message)
        return self._chat_quick(user_message)

    def _chat_quick(self, user_message: str) -> str:
        """Single fast LLM turn — no tool loop, but still stream tokens to the UI."""
        self._activity("Quick reply mode…")
        model, api_key = self._resolve_model()
        system = self.assembler.build_quick_prompt()
        text = self._call_model(
            model,
            api_key,
            system,
            step=0,
            stream=True,
            max_tokens=2048,
            history_limit=8,
        )
        from src.repl.response_clean import clean_assistant_text

        reply = clean_assistant_text(text.strip()) or text.strip()
        if reply:
            self._activity("Done.")
            self._history.append({"role": "assistant", "content": reply})
            return reply
        return "No response from model."

    def _chat_agentic(self, user_message: str) -> str:
        self._activity("Agent mode — tools until done")
        model, api_key = self._resolve_model()
        system = self.assembler.build_system_prompt() + "\n" + TOOL_SPEC
        last_natural = ""

        for step in range(1, MAX_AGENT_STEPS + 1):
            self._activity(f"Model step {step}/{MAX_AGENT_STEPS}…")
            text = self._call_model(model, api_key, system, step=step, stream=True)
            calls = extract_tool_calls(text)
            if not calls:
                from src.repl.response_clean import clean_assistant_text

                last_natural = clean_assistant_text(text.strip())
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
            for call in calls:
                self._activity(f"▸ Next action: {describe_tool_call(call)}")
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

    def _call_model(
        self,
        model: dict[str, Any],
        api_key: str,
        system: str,
        *,
        step: int = 0,
        stream: bool = True,
        max_tokens: int = 8192,
        history_limit: int = 16,
    ) -> str:
        model_id = str(model.get("id", self.ctx.config.get("default_model", "?")))
        display = model.get("display_name") or model_id
        self._activity(f"Calling {display}…")
        messages = [
            {"role": m["role"], "content": m["content"]}
            for m in self._history[-history_limit:]
        ]
        unified: dict[str, Any] = {
            "system_prompt": system,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3 if not stream else 0.2,
            "stream": stream,
        }
        url, headers, body = self.builder.build_request(unified, model, api_key=api_key)
        t0 = time.perf_counter()
        usage: dict[str, int] = {}
        text = ""

        if not stream:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(url, headers=headers, json=body)
                raw = resp.json() if resp.content else {}
                if resp.status_code >= 400:
                    err = self.parser.parse_error(raw, resp.status_code)
                    raise RuntimeError(err.get("message", str(raw)))
                parsed = self.parser.parse_response(raw, model, latency_ms=0)
                text = parsed.get("content", "") or ""
                usage = self.parser.extract_usage(raw, model)
        else:
            self._activity("Streaming…")
            accumulator: dict[str, Any] = {"content": ""}
            try:
                with httpx.Client(timeout=180.0) as client:
                    with client.stream("POST", url, headers=headers, json=body) as resp:
                        if resp.status_code >= 400:
                            raw = resp.read().decode("utf-8", errors="replace")
                            try:
                                import json as _json

                                payload = _json.loads(raw) if raw else {}
                            except Exception:
                                payload = {"error": raw}
                            err = self.parser.parse_error(payload, resp.status_code)
                            raise RuntimeError(err.get("message", str(payload)))
                        for line in resp.iter_lines():
                            if not line:
                                continue
                            delta = self.parser.parse_streaming_chunk(
                                line, model, accumulator
                            )
                            if delta:
                                self._on_stream(delta)
                        text = str(accumulator.get("content", "") or "")
            except (httpx.HTTPError, RuntimeError):
                raise
            except Exception:
                text = ""
            if not text.strip():
                unified.pop("stream", None)
                with httpx.Client(timeout=120.0) as client:
                    resp = client.post(url, headers=headers, json=body)
                    raw = resp.json() if resp.content else {}
                    if resp.status_code >= 400:
                        err = self.parser.parse_error(raw, resp.status_code)
                        raise RuntimeError(err.get("message", str(raw)))
                    parsed = self.parser.parse_response(raw, model, latency_ms=0)
                    text = parsed.get("content", "") or ""
                    usage = self.parser.extract_usage(raw, model)

        latency = (time.perf_counter() - t0) * 1000
        self._activity(f"Response ({latency:.0f} ms)")
        if usage:
            self._log_tokens(usage)
        inp = int(usage.get("input_tokens", 0))
        out = int(usage.get("output_tokens", 0))
        if inp or out:
            self._activity(f"Tokens: ↑{inp:,} ↓{out:,}")
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

        if name == "delete_file":
            path = str(args.get("path", ""))
            cat, detail = permission_for_tool(name, args)
            if cat and not self._permissions.ensure(cat, detail):
                return (
                    f"Error: delete denied by user ({path}). "
                    "Tell them to approve in the permission dialog, or use delete_file "
                    "after approval."
                )
            self._activity(f"🗑 Deleting file: {path}")
            return self.tools.delete_file(path)

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
            cat, detail = permission_for_command(cmd)
            if cat:
                if detail.startswith("Blocked dangerous"):
                    return f"Error: {detail}"
                if not self._permissions.ensure(cat, detail):
                    return (
                        "Error: command denied — user did not approve delete for this action. "
                        "Use delete_file tool instead, or ask them to allow delete for the session."
                    )
            preview = cmd if len(cmd) <= 100 else cmd[:97] + "…"
            self._activity(f"⚡ Running command: {preview}")
            result = self.tools.run_command(cmd, grants=self._permissions.grants)
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
