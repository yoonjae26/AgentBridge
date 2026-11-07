"""`agentbridge remote ...` - human-in-the-loop remote agent workflow."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape

from agentbridge.cli.context import handle_errors, open_project
from agentbridge.cli.output import console, styled
from agentbridge.errors import NotFoundError

remote_app = typer.Typer(help="Remote agent handoff (e.g. Antigravity).", no_args_is_help=True)


@remote_app.command("packet")
@handle_errors
def remote_packet(task_id: str) -> None:
    """Print the handoff packet generated for a remote task."""
    ctx = open_project()
    task = ctx.store.find_task(task_id)
    artifacts = task.extra.get("handoff_artifacts") or {}
    path = artifacts.get("packet_markdown")
    if not path or not Path(path).exists():
        raise NotFoundError(f"No handoff packet for {task.id}")
    console.print(Path(path).read_text(encoding="utf-8"), markup=False)


@remote_app.command("import")
@handle_errors
def remote_import(
    task_id: str,
    branch: Annotated[str, typer.Option("--branch", help="Branch containing the result.")],
    remote: Annotated[
        str | None,
        typer.Option("--remote", help="Git remote to fetch from (omit for a local branch)."),
    ] = None,
) -> None:
    """Fetch a remote agent's result branch and validate it locally."""
    ctx = open_project()
    task = ctx.store.find_task(task_id)
    report = asyncio.run(ctx.orchestrator().import_remote(task.id, branch, remote))
    task = ctx.store.get_task(task.id)
    console.print(f"Validation: {styled(report.outcome.value)}; task {styled(task.status)}")
    if task.status == "WAITING_FOR_APPROVAL":
        console.print(escape(f"Approve with: agentbridge tasks approve {task.id}"))
