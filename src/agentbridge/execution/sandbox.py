"""Docker sandbox for validation commands.

Validation executes code written by agents (tests, conftest.py, setup hooks). With
``validation.sandbox: docker`` each command runs in a throwaway container that only
sees the task worktree, has no network, and is resource-limited. Agent processes
themselves are not containerised by this module.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from agentbridge.config.settings import DockerSandboxSettings
from agentbridge.execution.process import resolve_executable

CONTAINER_WORKDIR = "/workspace"
_PASSTHROUGH_ENV = ("PYTHONDONTWRITEBYTECODE", "PYTEST_ADDOPTS", "RUFF_NO_CACHE")


def docker_available() -> bool:
    return resolve_executable("docker") is not None


def expand_for_container(command: list[str]) -> list[str]:
    """``{python}`` means the container's interpreter, not the host's."""
    return ["python" if part == "{python}" else part for part in command]


def wrap_command(
    inner: list[str], workdir: Path, settings: DockerSandboxSettings, env: dict[str, str]
) -> list[str]:
    args = [
        "docker",
        "run",
        "--rm",
        "--init",
        "--network",
        settings.network,
        "--memory",
        settings.memory,
        "--cpus",
        str(settings.cpus),
        "--pids-limit",
        str(settings.pids_limit),
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "-v",
        f"{workdir.resolve()}:{CONTAINER_WORKDIR}",
        "-w",
        CONTAINER_WORKDIR,
        "-e",
        "HOME=/tmp",
    ]
    if sys.platform != "win32" and hasattr(os, "getuid"):
        # Files created in the mounted worktree stay owned by the user.
        args += ["--user", f"{os.getuid()}:{os.getgid()}"]
    for name in _PASSTHROUGH_ENV:
        if name in env:
            args += ["-e", f"{name}={env[name]}"]
    return [*args, settings.image, *inner]
