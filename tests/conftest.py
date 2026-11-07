"""Shared fixtures."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from agentbridge.config.loader import ProjectPaths
from agentbridge.config.settings import (
    OrchestrationSettings,
    ProviderSettings,
    RoutingSettings,
    Settings,
    ValidationSettings,
)
from agentbridge.core.orchestrator import Orchestrator
from agentbridge.storage.database import Database
from agentbridge.storage.repositories import Store


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def make_repo(path: Path, files: dict[str, str] | None = None) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "Test User")
    git(path, "config", "user.email", "test@example.com")
    git(path, "config", "core.autocrlf", "false")
    git(path, "config", "commit.gpgsign", "false")
    for name, content in (files or {"README.md": "# sample\n"}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "initial")
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(
        tmp_path / "project",
        {"README.md": "# sample\n", "pytest.ini": "[pytest]\naddopts = -p no:cacheprovider\n"},
    )


def make_settings(**overrides: Any) -> Settings:
    providers = overrides.pop("providers", None) or {"mock": ProviderSettings(type="mock")}
    data: dict[str, Any] = {
        "providers": providers,
        "routing": overrides.pop("routing", RoutingSettings()),
        "orchestration": overrides.pop(
            "orchestration",
            OrchestrationSettings(retry_backoff_seconds=0, heartbeat_seconds=0.05),
        ),
        "validation": overrides.pop(
            "validation",
            ValidationSettings(run_lint=False, run_type_check=False, run_tests=True),
        ),
    }
    data.update(overrides)
    return Settings(**data)


OrchestratorFactory = Callable[..., Orchestrator]


@pytest.fixture
def orchestrator_factory(repo: Path) -> OrchestratorFactory:
    created: list[Database] = []

    def factory(
        settings: Settings | None = None, root: Path | None = None, **kw: Any
    ) -> Orchestrator:
        paths = ProjectPaths(root or repo)
        db = Database(paths.database)
        created.append(db)
        return Orchestrator(paths, settings or make_settings(), Store(db), **kw)

    yield factory  # type: ignore[misc]
    for db in created:
        db.close()
