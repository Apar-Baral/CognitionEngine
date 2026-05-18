"""Rich console permission prompts (line-mode REPL)."""

from __future__ import annotations

from rich.console import Console
from rich.prompt import Prompt

from src.agent.permissions import PermissionDecision


def ask_permission(console: Console, category: str, detail: str) -> PermissionDecision:
    console.print()
    console.print(f"[bold yellow]Permission required[/] — [cyan]{category}[/]")
    console.print(f"[white]{detail}[/]")
    choice = Prompt.ask(
        "[dim]Allow?[/]  [bold](o)[/]nce  [bold](s)[/]ession  [bold](n)[/]o",
        choices=["o", "s", "n", "once", "session", "no"],
        default="n",
        show_choices=False,
    )
    c = choice.lower().strip()
    if c in ("o", "once"):
        return PermissionDecision(allowed=True, remember_session=False)
    if c in ("s", "session"):
        return PermissionDecision(allowed=True, remember_session=True)
    return PermissionDecision(allowed=False)
