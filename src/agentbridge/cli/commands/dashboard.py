"""`agentbridge dashboard` - local web UI."""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Annotated

import typer

from agentbridge.cli.context import handle_errors
from agentbridge.cli.output import console
from agentbridge.config.loader import load_project
from agentbridge.errors import ConfigError

LOOPBACK = {"127.0.0.1", "localhost", "::1"}


@handle_errors
def dashboard_command(
    port: Annotated[int, typer.Option("--port", min=1024, max=65535)] = 8765,
    host: Annotated[str, typer.Option("--host", help="Loopback address only.")] = "127.0.0.1",
    no_browser: Annotated[bool, typer.Option("--no-browser")] = False,
    benchmarks_dir: Annotated[Path | None, typer.Option("--benchmarks-dir")] = None,
) -> None:
    """Start the local dashboard (runs, tasks, diffs, validation, approvals, benchmarks)."""
    if host not in LOOPBACK:
        raise ConfigError(
            "The dashboard can approve merges and only listens on loopback addresses",
            hint="Use --host 127.0.0.1 and an SSH tunnel for remote access.",
        )
    try:
        import uvicorn

        from agentbridge.dashboard.server import STATIC_DIR, create_app
    except ImportError as exc:
        raise ConfigError(
            "Dashboard dependencies are not installed",
            hint='pip install "agentbridge-core[dashboard]"',
        ) from exc
    paths, settings = load_project()
    paths.ensure()
    app = create_app(paths, settings, benchmarks_dir=benchmarks_dir)
    url = f"http://{host}:{port}/"
    if not (STATIC_DIR / "index.html").is_file():
        console.print(
            "[yellow]Frontend build not found; only the /api endpoints are served."
            "[/yellow] Build it with: cd dashboard && npm install && npm run build"
        )
    console.print(f"AgentBridge dashboard for [bold]{settings.project.name}[/bold]: {url}")
    console.print("[dim]Press Ctrl+C to stop.[/dim]")
    if not no_browser:
        webbrowser.open(url)
    uvicorn.run(app, host=host, port=port, log_level="warning")
