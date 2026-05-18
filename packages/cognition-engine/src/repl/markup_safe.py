"""Escape user/LLM text before embedding in Rich markup strings."""

from __future__ import annotations

from rich.markup import escape


def escape_markup(text: str) -> str:
    return str(escape(text))
