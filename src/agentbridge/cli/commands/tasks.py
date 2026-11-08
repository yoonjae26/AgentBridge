"""`run`, `tasks ...`, `logs` and `report` commands."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from agentbridge.cli.context import handle_errors, open_project
from agentbridge.cli.output import console, styled
from agentbridge.config.settings import PolicyProfile
from agentbridge.errors import ExitCode, NotFoundError
from agentbridge.reporting.generator import (
    build_task_report,
    next_steps,
    task_dict,
    write_run_report,
    write_task_report,
)
from agentbridge.tasks.models import TaskStatus

tasks_app = typer.Typer(help="Inspect and control tasks.", no_args_is_help=True)

MOCK_SCENARIOS = ("success", "failure", "delay", "interrupt", "invalid_output", "unavailable")


@handle_errors
def run_command(
    objective: Annotated[str, typer.Argument(help="What you want done.")],
    provider: Annotated[
        str | None, typer.Option("--provider", "-p", help="Provider for work tasks.")
    ] = None,
    planner: Annotated[
        str | None,
        typer.Option("--planner", help="Planner mode: single, standard or provider."),
    ] = None,
    policy: Annotated[
        PolicyProfile | None, typer.Option("--policy", help="Override security policy.")
    ] = None,
    mock_scenario: Annotated[
        str | None, typer.Option("--mock-scenario", help="Mock provider scenario.")
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print a JSON summary.")] = False,
) -> None:
    """Plan an objective, execute its tasks in isolated workspaces and validate them."""
    if planner and planner not in ("single", "standard", "provider"):
        raise typer.BadParameter("planner must be single, standard or provider")
    if mock_scenario and mock_scenario not in MOCK_SCENARIOS:
        raise typer.BadParameter(f"mock scenario must be one of {', '.join(MOCK_SCENARIOS)}")
    ctx = open_project()
    orchestrator = ctx.orchestrator(policy, quiet=as_json)
    recovered = orchestrator.recover()
    if recovered and not as_json:
        console.print(f"[yellow]Marked {len(recovered)} orphaned task(s) INTERRUPTED[/yellow]")

    async def go() -> tuple[str, dict[str, str]]:
        metadata = {"mock_scenario": mock_scenario} if mock_scenario else None
        run_id = await orchestrator.submit(
            objective, provider=provider, planner_mode=planner, metadata=metadata
        )
        if not as_json:
            console.print(f"Run [bold]{run_id}[/bold] created")
        summary = await orchestrator.execute_run(run_id)
        return run_id, summary.statuses

    run_id, statuses = asyncio.run(go())
    if as_json:
        console.print_json(json.dumps({"run_id": run_id, "tasks": statuses}))
    else:
        table = Table(title=f"Run {run_id}")
        table.add_column("Task")
        table.add_column("Status")
        table.add_column("Validation")
        for task in ctx.store.list_tasks(run_id=run_id):
            table.add_row(task.id, styled(task.status), styled(task.validation_outcome))
        console.print(table)
        for task in ctx.store.list_tasks(run_id=run_id):
            for step in next_steps(task):
                console.print(f"  {escape(step)}")
        console.print(f"Report: agentbridge report {run_id}")
    values = set(statuses.values())
    if TaskStatus.FAILED.value in values:
        validation_failed = any(
            t.validation_outcome == "FAIL" for t in ctx.store.list_tasks(run_id=run_id)
        )
        raise typer.Exit(
            int(ExitCode.VALIDATION_FAILED if validation_failed else ExitCode.TASK_FAILED)
        )
    if values == {TaskStatus.CANCELLED.value}:
        raise typer.Exit(int(ExitCode.CANCELLED))
    if TaskStatus.INTERRUPTED.value in values:
        raise typer.Exit(int(ExitCode.TASK_FAILED))


@tasks_app.command("list")
@handle_errors
def tasks_list(
    run: Annotated[str | None, typer.Option("--run", help="Only tasks of this run.")] = None,
    status: Annotated[
        str | None, typer.Option("--status", help="Filter by status, e.g. FAILED.")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="Max rows.")] = 50,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """List tasks (newest first)."""
    ctx = open_project()
    ctx.orchestrator(quiet=True).recover()
    statuses = [TaskStatus(status.upper())] if status else None
    tasks = ctx.store.list_tasks(run_id=run, statuses=statuses, limit=limit)
    if as_json:
        console.print_json(json.dumps([task_dict(t) for t in tasks], default=str))
        return
    if not tasks:
        console.print('No tasks yet. Try: agentbridge run "..." --provider mock')
        return
    table = Table()
    for column in ("Task", "Title", "Role", "Status", "Provider", "Validation", "Created"):
        table.add_column(column, overflow="fold")
    for t in tasks:
        table.add_row(
            t.id,
            escape(t.title[:50]),
            t.role,
            styled(t.status),
            t.assigned_provider or "-",
            styled(t.validation_outcome),
            t.created_at[:19],
        )
    console.print(table)


@tasks_app.command("status")
@handle_errors
def tasks_status(task_id: str) -> None:
    """Show the current status of a task."""
    ctx = open_project()
    ctx.orchestrator(quiet=True).recover()
    task = ctx.store.find_task(task_id)
    console.print(
        f"[bold]{task.id}[/bold] {styled(task.status)}"
        + (f" ({task.waiting_reason})" if task.waiting_reason else "")
    )
    console.print(f"  {escape(task.title)}")
    console.print(
        f"  provider: {task.assigned_provider or '-'}  retries: {task.retry_count}  "
        f"validation: {task.validation_outcome or '-'}"
    )
    if task.error_message:
        console.print(f"  [red]error:[/red] {escape(task.error_message[:500])}")
    for step in next_steps(task):
        console.print(f"  next: {escape(step)}")


@tasks_app.command("inspect")
@handle_errors
def tasks_inspect(task_id: str) -> None:
    """Show full task details, executions and the latest validation."""
    ctx = open_project()
    task = ctx.store.find_task(task_id)
    report = build_task_report(ctx.store, task.id)
    console.print_json(json.dumps(report, default=str))


@tasks_app.command("resume")
@handle_errors
def tasks_resume(
    task_id: str,
    rerun: Annotated[
        bool, typer.Option("--rerun", help="Explicitly re-execute the agent.")
    ] = False,
    revalidate: Annotated[
        bool, typer.Option("--revalidate", help="Re-run validation of a waiting task.")
    ] = False,
) -> None:
    """Safely resume an interrupted, failed or pending task."""
    ctx = open_project()
    task = ctx.store.find_task(task_id)
    status = asyncio.run(ctx.orchestrator().resume(task.id, rerun=rerun, revalidate=revalidate))
    console.print(f"{task.id}: {styled(status)}")


@tasks_app.command("cancel")
@handle_errors
def tasks_cancel(task_id: str) -> None:
    """Cancel a task (signals the running agent if it is executing)."""
    ctx = open_project()
    task = ctx.store.find_task(task_id)
    console.print(ctx.orchestrator(quiet=True).request_cancel(task.id))


@tasks_app.command("approve")
@handle_errors
def tasks_approve(task_id: str) -> None:
    """Approve a validated task and merge its branch into the base branch."""
    ctx = open_project()
    task = ctx.store.find_task(task_id)
    message = ctx.orchestrator(quiet=True).approve(task.id)
    console.print(f"[green]{escape(message)}[/green]")


@tasks_app.command("reject")
@handle_errors
def tasks_reject(
    task_id: str,
    reason: Annotated[str, typer.Option("--reason")] = "Rejected by user",
) -> None:
    """Reject a task awaiting approval. Its branch and worktree are kept."""
    ctx = open_project()
    task = ctx.store.find_task(task_id)
    ctx.orchestrator(quiet=True).reject(task.id, reason)
    console.print(f"{task.id} rejected. Branch {task.git_branch or '-'} was kept.")


@tasks_app.command("cleanup")
@handle_errors
def tasks_cleanup(task_id: str) -> None:
    """Remove a finished task's worktree (only if clean). The branch is kept."""
    ctx = open_project()
    task = ctx.store.find_task(task_id)
    if task.status not in (
        TaskStatus.SUCCEEDED.value,
        TaskStatus.CANCELLED.value,
        TaskStatus.FAILED.value,
    ):
        raise NotFoundError(f"Task {task.id} is {task.status}; only finished tasks are cleaned")
    if task.workspace_kind != "git_worktree" or not task.workspace_path:
        console.print("No git worktree to remove.")
        return
    orchestrator = ctx.orchestrator(quiet=True)
    orchestrator.workspaces.remove_worktree(Path(task.workspace_path))
    ctx.store.add_event(
        "workspace.removed", f"Removed {task.workspace_path}", task_id=task.id, run_id=task.run_id
    )
    console.print(f"Removed worktree {task.workspace_path}; branch {task.git_branch} kept.")


@handle_errors
def logs_command(
    task_id: str,
    tail: Annotated[int, typer.Option("--tail", help="Lines of agent output.")] = 40,
) -> None:
    """Show a task's event history and the tail of the latest agent output."""
    ctx = open_project()
    task = ctx.store.find_task(task_id)
    for ev in ctx.store.list_events(task_id=task.id):
        transition = f" {ev.from_status or ''}->{ev.to_status}" if ev.to_status else ""
        console.print(f"[dim]{ev.created_at[:23]}[/dim] {ev.type}{transition} {escape(ev.message)}")
    executions = ctx.store.list_executions(task.id)
    if executions and executions[-1].output_path:
        path = Path(executions[-1].output_path)
        if path.exists():
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            console.print(f"\n[bold]Agent output[/bold] ({path}, last {tail} lines):")
            for line in lines[-tail:]:
                console.print(escape(line))


@handle_errors
def report_command(
    ref: Annotated[str, typer.Argument(help="Task id (or prefix) or run id.")],
    fmt: Annotated[str, typer.Option("--format", help="markdown or json")] = "markdown",
) -> None:
    """Generate (and print) the final report for a task or a run."""
    ctx = open_project()
    reports_dir = ctx.paths.reports_dir
    try:
        run = ctx.store.get_run(ref)
        json_path, md_path = write_run_report(ctx.store, run.id, reports_dir)
        for task in ctx.store.list_tasks(run_id=run.id):
            write_task_report(ctx.store, task.id, reports_dir)
    except NotFoundError:
        task = ctx.store.find_task(ref)
        json_path, md_path = write_task_report(ctx.store, task.id, reports_dir)
    if fmt == "json":
        # Raw, unwrapped JSON on stdout so it can be piped to other tools.
        typer.echo(json_path.read_text(encoding="utf-8").rstrip())
        typer.echo(f"Saved: {md_path} and {json_path}", err=True)
        return
    console.print(md_path.read_text(encoding="utf-8"), markup=False, soft_wrap=True)
    console.print(f"[dim]Saved: {md_path} and {json_path}[/dim]")
