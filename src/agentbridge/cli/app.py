"""AgentBridge command-line interface."""

from __future__ import annotations

from typing import Annotated

import typer

from agentbridge import __version__
from agentbridge.cli.commands.bench import bench_app
from agentbridge.cli.commands.dashboard import dashboard_command
from agentbridge.cli.commands.project import init_command, providers_app
from agentbridge.cli.commands.remote import remote_app
from agentbridge.cli.commands.tasks import logs_command, report_command, run_command, tasks_app

app = typer.Typer(
    name="agentbridge",
    help="One interface. Multiple AI agents. Reliable software delivery.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    add_completion=False,
)


def _version(value: bool) -> None:
    if value:
        typer.echo(f"agentbridge {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version, is_eager=True, help="Show the version."),
    ] = None,
) -> None:
    """AgentBridge orchestrates AI coding agents and AgentBench measures them."""


app.command("init")(init_command)
app.command("run")(run_command)
app.command("logs")(logs_command)
app.command("report")(report_command)
app.command("dashboard")(dashboard_command)
app.add_typer(providers_app, name="providers")
app.add_typer(tasks_app, name="tasks")
app.add_typer(remote_app, name="remote")
app.add_typer(bench_app, name="benchmark")
