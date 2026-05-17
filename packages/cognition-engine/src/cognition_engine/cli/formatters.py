from rich.console import Console
from rich.panel import Panel

console = Console()


def print_success(msg: str) -> None:
    console.print(f"[green]OK[/green] {msg}")


def print_error(msg: str) -> None:
    console.print(f"[red]ERR[/red] {msg}")


def print_info(msg: str) -> None:
    console.print(f"[cyan]{msg}[/cyan]")


def print_panel(title: str, body: str) -> None:
    console.print(Panel(body, title=title, border_style="blue"))
