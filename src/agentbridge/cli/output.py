"""Console output helpers."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape

console = Console(highlight=False)
err_console = Console(stderr=True, highlight=False)

STATUS_STYLES = {
    "PENDING": "dim",
    "READY": "cyan",
    "QUEUED": "cyan",
    "RUNNING": "bold blue",
    "WAITING_FOR_APPROVAL": "bold yellow",
    "VALIDATING": "blue",
    "INTEGRATING": "magenta",
    "SUCCEEDED": "bold green",
    "FAILED": "bold red",
    "CANCELLED": "dim red",
    "INTERRUPTED": "bold magenta",
    "PASS": "green",
    "FAIL": "red",
    "WARNING": "yellow",
    "NEEDS_HUMAN_REVIEW": "bold yellow",
    "SKIPPED": "dim",
}


def styled(status: str | None) -> str:
    if status is None:
        return "[dim]-[/dim]"
    style = STATUS_STYLES.get(status, "")
    return f"[{style}]{escape(status)}[/{style}]" if style else escape(status)


def error(message: str, hint: str | None = None) -> None:
    err_console.print(f"[bold red]Error:[/bold red] {escape(message)}")
    if hint:
        err_console.print(f"[dim]Hint:[/dim] {escape(hint)}")


def progress(type_: str, message: str, task_id: str | None) -> None:
    prefix = f"[dim]{escape(task_id)}[/dim] " if task_id else ""
    if type_ == "task.transition":
        status, _, rest = message.partition(":")
        console.print(f"  {prefix}{styled(status)}{escape(':' + rest) if rest else ''}")
    elif type_ in ("plan.warning", "task.error"):
        console.print(f"  {prefix}[yellow]{escape(message)}[/yellow]")
    else:
        console.print(f"  {prefix}[dim]{escape(message)}[/dim]")
