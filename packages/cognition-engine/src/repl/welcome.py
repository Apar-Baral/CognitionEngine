"""Welcome / getting-started text for the agent console chat log."""


def welcome_markup(*, project_root: str, initialized: bool, goal: str = "") -> str:
    lines = [
        "[bold #58a6ff]Cognition Engine[/] — agent console",
        "",
        "[bold]Quick start[/]",
        "  1. [bold]Setup keys[/] (sidebar) or [bold]/setup[/] — API keys + model",
        "  2. [bold]Generate plan[/] or [bold]/plan[/] — phased roadmap in DNA",
        "  3. [bold]Start session[/] or [bold]/start[/] — writes bootstrap context",
        "  4. Ask in chat or use tools: create files, run commands, /status, /shield",
        "  5. [bold]End session[/] or [bold]/end summary[/] — saves memory + RL budgets",
        "",
        "[bold]Copy & clipboard[/]",
        "  Drag to select inside the [bold]chat[/] or [bold]trace[/] pane (labels do not select).",
        "  Terminal copy (Linux Ctrl+Shift+C): set [dim]CE_NATIVE_COPY=1[/] before launch — "
        "disables in-app mouse; use [dim]PgUp[/]/[dim]PgDn[/] to scroll.",
        "  Backup file after each reply: [dim]~/.cognition/last_reply.txt[/]",
        "",
        "[bold]Scroll[/]",
        "  Click chat or trace, then [dim]PgUp[/] / [dim]PgDn[/]  ·  mouse wheel when CE mouse is on",
        "",
        "[bold]Slash commands[/]",
        "  /help /setup /plan /start /end /status /shield /memory /keys /model",
        "",
        "[bold]Built-in features[/]",
        "  Planner · Hallucination Shield · session memory · Q-learning token RL · budgets",
        "",
        f"[dim]Project:[/] {project_root}",
    ]
    if initialized and goal:
        g = goal if len(goal) <= 120 else goal[:117] + "…"
        lines.append(f"[dim]Goal:[/] {g}")
    elif not initialized:
        lines.append("[yellow]Run Setup keys to initialize this folder.[/]")
    return "\n".join(lines)
