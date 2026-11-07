"""`agentbridge init` and `agentbridge providers ...`."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from rich.table import Table

from agentbridge.agents.registry import AgentRegistry
from agentbridge.cli.context import handle_errors
from agentbridge.cli.output import console
from agentbridge.config.loader import ProjectPaths, load_project, write_config
from agentbridge.config.settings import CONFIG_FILENAME, default_config_dict
from agentbridge.errors import ConfigError, ExitCode
from agentbridge.storage.database import Database
from agentbridge.workspace.git import Git, git_available
from agentbridge.workspace.manager import ensure_state_dir_excluded

providers_app = typer.Typer(help="Inspect configured agent providers.", no_args_is_help=True)


@handle_errors
def init_command(
    path: Annotated[Path, typer.Option("--path", help="Project directory.")] = Path("."),
    name: Annotated[str | None, typer.Option("--name", help="Project name.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite agentbridge.yaml.")] = False,
) -> None:
    """Initialise AgentBridge in a repository (creates agentbridge.yaml and .agentbridge/)."""
    root = path.resolve()
    if not root.is_dir():
        raise ConfigError(f"Directory does not exist: {root}")
    paths = ProjectPaths(root)
    git = Git(root)
    is_repo = git_available() and git.is_repository()
    branch = (git.current_branch() if is_repo else None) or "main"
    if paths.config_file.exists() and not force:
        console.print(
            f"[yellow]{CONFIG_FILENAME} already exists[/yellow]; keeping it "
            "(use --force to regenerate)."
        )
    else:
        write_config(paths.config_file, default_config_dict(name or root.name, branch))
        console.print(f"[green]Created[/green] {paths.config_file}")
    paths.ensure()
    Database(paths.database).close()
    console.print(f"[green]Initialised[/green] state directory {paths.state_dir}")
    if is_repo:
        ensure_state_dir_excluded(git.toplevel() if git.toplevel() == root else root)
        console.print("Added .agentbridge/ to .git/info/exclude (your .gitignore is untouched)")
        if not git.has_commits():
            console.print(
                "[yellow]Warning:[/yellow] the repository has no commits yet; "
                "create one before running tasks with worktrees."
            )
    else:
        console.print(
            "[yellow]Warning:[/yellow] not a git repository. Local tasks need git "
            "worktrees: run 'git init' and make an initial commit."
        )
    console.print(
        f"Python {sys.version.split()[0]}; git {'found' if git_available() else 'MISSING'}"
    )
    console.print("Next: [bold]agentbridge providers check[/bold]")


@providers_app.command("list")
@handle_errors
def providers_list() -> None:
    """List configured providers and their declared capabilities."""
    _, settings = load_project()
    registry = AgentRegistry(settings)
    table = Table(title="Providers")
    for column in ("Name", "Type", "Enabled", "Execution", "Capabilities"):
        table.add_column(column)
    for name in registry.names():
        adapter = registry.get(name, require_enabled=False)
        caps = asyncio.run(adapter.get_capabilities())
        table.add_row(
            name,
            adapter.provider_type,
            "yes" if registry.is_enabled(name) else "no",
            caps.execution.value,
            ", ".join(sorted(c.value for c in caps.capabilities)),
        )
    console.print(table)
    routing = settings.routing
    console.print(
        f"Routing: planner={routing.planner}, default_worker={routing.default_worker}, "
        f"reviewer={routing.reviewer or '-'}"
    )


@providers_app.command("check")
@handle_errors
def providers_check(
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    """Check availability of every enabled provider. Exits 3 if any is unavailable."""
    _, settings = load_project()
    registry = AgentRegistry(settings)

    async def gather() -> dict[str, dict[str, object]]:
        results: dict[str, dict[str, object]] = {}
        for name in registry.names():
            adapter = registry.get(name, require_enabled=False)
            report = await adapter.check_availability()
            caps = await adapter.get_capabilities()
            results[name] = {
                "enabled": registry.is_enabled(name),
                "type": adapter.provider_type,
                "execution": caps.execution.value,
                **report.model_dump(),
            }
        return results

    results = asyncio.run(gather())
    if as_json:
        console.print_json(json.dumps(results))
    else:
        for name, info in results.items():
            mark = "[green]available[/green]" if info["available"] else "[red]unavailable[/red]"
            if not info["enabled"]:
                mark += " [dim](disabled)[/dim]"
            console.print(f"[bold]{name}[/bold] ({info['type']}, {info['execution']}): {mark}")
            if info.get("version"):
                console.print(f"    version: {escape(str(info['version']))}")
            console.print(f"    auth: {info['auth']}")
            for detail in info["details"]:  # type: ignore[attr-defined]
                console.print(f"    - {escape(str(detail))}")
    if any(info["enabled"] and not info["available"] for info in results.values()):
        raise typer.Exit(int(ExitCode.PROVIDER_UNAVAILABLE))
