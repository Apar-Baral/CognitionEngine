"""Optional LLM-assisted plan enrichment."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from src.cli.context import ProjectContext
from src.models.request_builder import RequestBuilder
from src.models.response_parser import ResponseParser


def enrich_phases_with_llm(
    ctx: ProjectContext,
    phases: list[dict[str, Any]],
    goal: str,
    *,
    max_phases: int = 8,
) -> list[dict[str, Any]]:
    """Ask LLM for tailored descriptions for first N phases."""
    model_id = str(ctx.config.get("default_model", "gpt-4o-mini"))
    reg = ctx.model_registry()
    model = reg.get_model(model_id) or reg.get_default_model()
    if not model:
        return phases
    provider = model.get("provider", "openai")
    key = ctx.config.get_api_key(provider) or ctx.config.get_api_key("openai")
    if not key:
        return phases

    names = [f"{p['id']}: {p['name']}" for p in phases[:max_phases]]
    prompt = (
        f"Project goal: {goal}\n\n"
        f"Phases: {', '.join(names)}\n\n"
        "Return JSON array of objects with keys id, description (one sentence each). "
        "Only JSON, no markdown."
    )
    builder = RequestBuilder()
    parser = ResponseParser()
    unified = {
        "system_prompt": "You are a software project planner. Output valid JSON only.",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
        "temperature": 0.2,
    }
    url, headers, body = builder.build_request(unified, model, api_key=key)
    try:
        with httpx.Client(timeout=60.0) as client:
            resp = client.post(url, headers=headers, json=body)
            raw = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                return phases
        parsed = parser.parse_response(raw, model)
        text = (parsed.get("content") or "").strip()
        text = re.sub(r"^```json\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        items = json.loads(text)
        if not isinstance(items, list):
            return phases
        by_id = {str(x.get("id")): str(x.get("description", "")) for x in items if isinstance(x, dict)}
        for p in phases:
            if p["id"] in by_id and by_id[p["id"]]:
                p["description"] = by_id[p["id"]]
    except Exception:
        return phases
    return phases
