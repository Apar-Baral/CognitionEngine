"""
Interactive CLI prompts with Rich styling.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt

console = Console()


class PromptCancelled(Exception):
    """User interrupted with Ctrl+C."""


def _handle_interrupt() -> None:
    console.print("\n[yellow]Cancelled.[/yellow]")
    raise PromptCancelled("Operation cancelled by user")


def confirm(question: str, default: bool = True) -> bool:
    try:
        return Confirm.ask(f"[bold cyan]{question}[/bold cyan]", default=default)
    except EOFError:
        return default
    except KeyboardInterrupt:
        _handle_interrupt()
        return False


def select(question: str, options: list[dict[str, str]]) -> str:
    console.print(f"[bold cyan]{question}[/bold cyan]")
    for i, opt in enumerate(options, 1):
        desc = opt.get("description", "")
        line = f"  {i}. {opt.get('name', '')}"
        if desc:
            line += f" [dim]— {desc}[/dim]"
        console.print(line)
    try:
        choice = IntPrompt.ask("Choose", default=1)
        idx = max(1, min(len(options), choice)) - 1
        return options[idx].get("value", options[idx].get("name", ""))
    except (KeyboardInterrupt, EOFError):
        _handle_interrupt()
        return options[0].get("value", "")


def ask_text(
    question: str,
    default: str = "",
    validator: Callable[[str], bool] | None = None,
) -> str:
    try:
        while True:
            val = Prompt.ask(f"[bold cyan]{question}[/bold cyan]", default=default or None)
            if validator is None or validator(val):
                return val
            console.print("[red]Invalid input. Try again.[/red]")
    except (KeyboardInterrupt, EOFError):
        _handle_interrupt()
        return default


def ask_number(
    question: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
    default: int | None = None,
) -> int:
    try:
        while True:
            val = IntPrompt.ask(f"[bold cyan]{question}[/bold cyan]", default=default)
            if minimum is not None and val < minimum:
                console.print(f"[red]Must be at least {minimum}[/red]")
                continue
            if maximum is not None and val > maximum:
                console.print(f"[red]Must be at most {maximum}[/red]")
                continue
            return val
    except (KeyboardInterrupt, EOFError):
        _handle_interrupt()
        return default or minimum or 0


def ask_path(question: str, *, must_exist: bool = True, default: str = "") -> Path:
    try:
        while True:
            val = Prompt.ask(f"[bold cyan]{question}[/bold cyan]", default=default or None)
            path = Path(val).expanduser().resolve()
            if must_exist and not path.exists():
                console.print("[red]Path does not exist.[/red]")
                continue
            return path
    except (KeyboardInterrupt, EOFError):
        _handle_interrupt()
        return Path(default or ".").resolve()


def ask_multi_select(question: str, options: list[str]) -> list[str]:
    console.print(f"[bold cyan]{question}[/bold cyan] (comma-separated numbers, e.g. 1,3)")
    for i, opt in enumerate(options, 1):
        console.print(f"  {i}. {opt}")
    try:
        raw = Prompt.ask("Select", default="")
        if not raw.strip():
            return []
        indices = {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}
        return [options[i - 1] for i in indices if 1 <= i <= len(options)]
    except (KeyboardInterrupt, EOFError):
        _handle_interrupt()
        return []


def ask_with_preview(preview: str, question: str = "Proceed?") -> bool:
    console.print(Panel(preview, border_style="dim"))
    return confirm(question, default=True)
