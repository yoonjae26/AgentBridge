"""Shared CLI plumbing: project loading and error handling."""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import typer

from agentbridge.cli.output import error, progress
from agentbridge.config.loader import ProjectPaths, load_project
from agentbridge.config.settings import PolicyProfile, Settings
from agentbridge.core.orchestrator import Orchestrator
from agentbridge.errors import AgentBridgeError, ExitCode
from agentbridge.storage.database import Database
from agentbridge.storage.repositories import Store


@dataclass
class ProjectContext:
    paths: ProjectPaths
    settings: Settings
    store: Store

    def orchestrator(
        self, policy: PolicyProfile | None = None, quiet: bool = False
    ) -> Orchestrator:
        return Orchestrator(
            self.paths,
            self.settings,
            self.store,
            policy_profile=policy,
            on_event=None if quiet else progress,
        )


def open_project(start: Path | None = None) -> ProjectContext:
    paths, settings = load_project(start)
    paths.ensure()
    return ProjectContext(paths, settings, Store(Database(paths.database)))


def handle_errors[F: Callable[..., Any]](func: F) -> F:
    """Convert expected errors into readable messages and stable exit codes."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except AgentBridgeError as exc:
            error(exc.message, exc.hint)
            raise typer.Exit(int(exc.exit_code)) from None
        except KeyboardInterrupt:
            error("Interrupted by user")
            raise typer.Exit(int(ExitCode.CANCELLED)) from None

    return wrapper  # type: ignore[return-value]
