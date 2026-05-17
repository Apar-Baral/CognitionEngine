"""
Transparent async HTTP proxy for LLM API calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web
import httpx

from src.memory.operational_memory import OperationalMemory
from src.proxy.budget_enforcer import BudgetEnforcer
from src.proxy.token_counter import TokenCounter

logger = logging.getLogger(__name__)

PROVIDER_UPSTREAM = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com",
    "deepseek": "https://api.deepseek.com",
}


@dataclass
class ProxyConfig:
    """Proxy server and upstream configuration."""

    host: str = "127.0.0.1"
    port: int = 8787
    provider_endpoints: dict[str, str] = field(default_factory=lambda: dict(PROVIDER_UPSTREAM))
    max_retries: int = 2
    retry_delay_seconds: float = 0.5


class ApiProxy:
    """Async context manager HTTP proxy for LLM APIs."""

    def __init__(
        self,
        config: ProxyConfig,
        token_counter: TokenCounter,
        budget_enforcer: BudgetEnforcer,
        operational_memory: OperationalMemory,
        session_id: int,
        *,
        cost_projector: Any | None = None,
    ) -> None:
        self.config = config
        self.token_counter = token_counter
        self.budget_enforcer = budget_enforcer
        self.operational_memory = operational_memory
        self.session_id = session_id
        self.cost_projector = cost_projector
        self._client: httpx.AsyncClient | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._request_count = 0
        self._in_flight_wrap_up = False
        self.session_state: dict[str, Any] = {
            "session_id": session_id,
            "tokens_used": 0,
            "zone": "green",
            "elapsed_seconds": 0.0,
            "request_count": 0,
        }

    async def __aenter__(self) -> ApiProxy:
        await self.start()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.shutdown()

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=120.0)
        app = web.Application()
        app.router.add_route("*", "/{path:.*}", self._aiohttp_handler)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(
            self._runner, self.config.host, self.config.port
        )
        await self._site.start()
        logger.info("ApiProxy listening on %s:%s", self.config.host, self.config.port)

    async def shutdown(self) -> None:
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()
        if self._client:
            await self._client.aclose()
        status = self.budget_enforcer.get_budget_status()
        logger.info(
            "ApiProxy shutdown session=%s tokens=%s zone=%s requests=%s",
            self.session_id,
            status["tokens_used"],
            status["zone"],
            self._request_count,
        )

    @property
    def base_url(self) -> str:
        return f"http://{self.config.host}:{self.config.port}"

    async def _aiohttp_handler(self, request: web.Request) -> web.StreamResponse:
        body = await request.read()
        headers = {k: request.headers.get(k) for k in request.headers if k.lower() != "host"}
        try:
            request_body = json.loads(body) if body else {}
        except json.JSONDecodeError:
            request_body = {}
        if request_body.get("stream"):
            return await self._forward_streaming(
                request, request.method, request.path, headers, request_body
            )
        return await self.handle_request(
            method=request.method,
            path=request.path,
            headers=headers,
            body=body,
        )

    async def handle_request(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> web.Response:
        """Core proxy logic for each HTTP request."""
        self._request_count += 1
        started = time.perf_counter()

        try:
            request_body = json.loads(body) if body else {}
        except json.JSONDecodeError:
            request_body = {}

        model_id = request_body.get("model", "unknown")
        provider, upstream_base = self._resolve_provider(path, headers)

        check = self.budget_enforcer.check_budget()
        if not check["continue"] and not self._in_flight_wrap_up:
            return self._error_response(
                429,
                {
                    "error": "budget_exhausted",
                    "message": check.get("warning", "Token budget exhausted"),
                    "session": self.budget_enforcer.get_budget_status(),
                },
            )

        if self.budget_enforcer.should_block_new_task(request_body):
            return self._error_response(
                429,
                {
                    "error": "wrap_up_required",
                    "message": (
                        "Session is in wrap-up mode. Complete the handoff summary; "
                        "do not start new tasks."
                    ),
                },
            )

        inject = self.budget_enforcer.consume_pending_injection()
        if inject:
            request_body = self._inject_system_message(request_body, inject, provider)

        input_tokens = self.token_counter.count_input_tokens(request_body, model_id)

        upstream_url = f"{upstream_base.rstrip('/')}{path}"
        try:
            response = await self._forward_with_retry(
                method, upstream_url, headers, request_body
            )
        except httpx.HTTPError as exc:
            logger.exception("Upstream error")
            return self._error_response(
                502,
                {"error": "bad_gateway", "message": f"Provider unreachable: {exc}"},
            )

        latency_ms = (time.perf_counter() - started) * 1000
        resp_body: dict[str, Any] = {}
        try:
            resp_body = response.json()
        except Exception:
            resp_body = {"raw": response.text[:500]}

        usage = resp_body.get("usage") or {}
        official_out = usage.get("output_tokens") or usage.get("completion_tokens")
        if official_out is not None and usage.get("input_tokens") is not None:
            in_t = int(usage["input_tokens"])
            out_t = int(usage["output_tokens"])
            self.token_counter.accuracy_validation(input_tokens, in_t, model_id, "input")
            output_tokens = self.token_counter.accuracy_validation(
                self.token_counter.count_output_tokens(resp_body, model_id),
                int(official_out),
                model_id,
                "output",
            )
        else:
            output_tokens = self.token_counter.count_output_tokens(resp_body, model_id)

        total = input_tokens + output_tokens
        self.budget_enforcer.add_usage(total)
        self._update_session_state()

        purpose = _extract_purpose(request_body)
        self.operational_memory.log_api_call(
            model_id=model_id,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            purpose=purpose,
            latency_ms=latency_ms,
            succeeded=response.status_code < 400,
        )
        if self.cost_projector:
            self.cost_projector.record_call(model_id, input_tokens, output_tokens)

        return web.Response(
            status=response.status_code,
            body=response.content,
            headers=dict(response.headers),
        )

    async def _forward_streaming(
        self,
        aiohttp_request: web.Request,
        method: str,
        path: str,
        headers: dict[str, str],
        request_body: dict[str, Any],
    ) -> web.StreamResponse:
        assert self._client is not None
        started = time.perf_counter()
        model_id = request_body.get("model", "unknown")
        provider, upstream_base = self._resolve_provider(path, headers)
        upstream_url = f"{upstream_base.rstrip('/')}{path}"

        check = self.budget_enforcer.check_budget()
        if not check["continue"]:
            return self._error_response(429, {"error": "budget_exhausted"})

        inject = self.budget_enforcer.consume_pending_injection()
        if inject:
            request_body = self._inject_system_message(request_body, inject, provider)

        input_tokens = self.token_counter.count_input_tokens(request_body, model_id)
        accumulated: list[str] = []
        stream_response = web.StreamResponse()
        await stream_response.prepare(aiohttp_request)

        async with self._client.stream(
            method, upstream_url, headers=headers, json=request_body
        ) as upstream:
            stream_response.set_status(upstream.status_code)
            async for chunk in upstream.aiter_bytes():
                await stream_response.write(chunk)
                text = chunk.decode("utf-8", errors="replace")
                for line in text.split("\n"):
                    if line.startswith("data: ") and line != "data: [DONE]":
                        try:
                            data = json.loads(line[6:])
                            delta = (
                                data.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if delta:
                                accumulated.append(delta)
                        except json.JSONDecodeError:
                            pass

        output_tokens = self.token_counter.add_streaming_output("".join(accumulated), model_id)
        self.budget_enforcer.add_usage(input_tokens + output_tokens)
        self._update_session_state()
        self.operational_memory.log_api_call(
            model_id=model_id,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            purpose="streaming",
            latency_ms=(time.perf_counter() - started) * 1000,
            succeeded=True,
        )
        return stream_response

    async def _forward_with_retry(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        request_body: dict[str, Any],
    ) -> httpx.Response:
        assert self._client is not None
        last_exc: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                return await self._client.request(
                    method, url, headers=headers, json=request_body
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.retry_delay_seconds)
        raise last_exc or httpx.HTTPError("upstream failed")

    def _resolve_provider(
        self, path: str, headers: dict[str, str]
    ) -> tuple[str, str]:
        if "/v1/messages" in path:
            return "anthropic", self.config.provider_endpoints.get(
                "anthropic", PROVIDER_UPSTREAM["anthropic"]
            )
        if "/v1/chat/completions" in path:
            host = headers.get("Host", "").lower()
            if "deepseek" in host:
                return "deepseek", self.config.provider_endpoints.get(
                    "deepseek", PROVIDER_UPSTREAM["deepseek"]
                )
            return "openai", self.config.provider_endpoints.get(
                "openai", PROVIDER_UPSTREAM["openai"]
            )
        return "openai", self.config.provider_endpoints.get(
            "openai", PROVIDER_UPSTREAM["openai"]
        )

    def _inject_system_message(
        self,
        body: dict[str, Any],
        message: str,
        provider: str,
    ) -> dict[str, Any]:
        body = dict(body)
        if provider == "anthropic":
            existing = body.get("system", "")
            if isinstance(existing, str):
                body["system"] = f"{existing}\n\n{message}".strip()
            else:
                body["system"] = message
        else:
            messages = list(body.get("messages", []))
            if messages and messages[0].get("role") == "system":
                content = messages[0].get("content", "")
                if isinstance(content, str):
                    messages[0] = {
                        "role": "system",
                        "content": f"{content}\n\n{message}",
                    }
            else:
                messages.insert(0, {"role": "system", "content": message})
            body["messages"] = messages
        return body

    def _update_session_state(self) -> None:
        status = self.budget_enforcer.get_budget_status()
        self.session_state = {
            "session_id": self.session_id,
            "tokens_used": status["tokens_used"],
            "zone": status["zone"],
            "request_count": self._request_count,
            "percentage_used": status["percentage_used"],
            "wrap_up_mode": self.budget_enforcer.wrap_up_mode,
        }

    @staticmethod
    def _error_response(status: int, payload: dict[str, Any]) -> web.Response:
        return web.Response(
            status=status,
            text=json.dumps(payload),
            content_type="application/json",
        )


def _extract_purpose(request_body: dict[str, Any]) -> str:
    messages = request_body.get("messages", [])
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content[:120]
    return ""
