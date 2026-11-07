"""Run Claude Code inside a locked-down container.

Privacy and safety properties:
- No host directory except the task worktree is mounted. ``~/.claude`` (login
  credentials, conversation history, settings) is never mounted.
- Authentication: exactly one environment variable (``CLAUDE_CODE_OAUTH_TOKEN`` from
  ``claude setup-token``, or ``ANTHROPIC_API_KEY``) is passed through **by name**
  (``-e NAME``), so its value never appears on a command line, in a log or in the
  image. No other host environment variables enter the container.
- Root filesystem is read-only; ``/tmp`` and the home directory are tmpfs, so no
  session data survives the run (``--rm``).
- Runs as an unprivileged user with all capabilities dropped and
  ``no-new-privileges``; memory, CPU and process limits apply.
- Shell, web fetch and web search tools are disallowed by default.

Limits: the container needs outbound network to reach the Anthropic API, so network
access cannot be disabled; the token is visible to the agent process itself.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from agentbridge.config.settings import AgentContainerSettings
from agentbridge.execution.sandbox import to_wsl_path

CONTAINER_HOME = "/home/node"
CONTAINER_WORKDIR = "/workspace"
_DOCKER_ENV = (
    "PATH",
    "SYSTEMROOT",
    "SystemRoot",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "HOME",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
)


def uses_wsl(settings: AgentContainerSettings) -> bool:
    return settings.command[0].lower() in ("wsl", "wsl.exe")


def container_name(execution_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in execution_id)
    return f"agentbridge-{safe}"[:63]


def docker_run_args(
    settings: AgentContainerSettings, workdir: Path, execution_id: str, claude_args: list[str]
) -> list[str]:
    via_wsl = uses_wsl(settings)
    mount = to_wsl_path(workdir) if via_wsl else str(workdir.resolve())
    user = "1000:1000"
    if not via_wsl and sys.platform != "win32" and hasattr(os, "getuid"):
        user = f"{os.getuid()}:{os.getgid()}"
    args = [
        *settings.command,
        "run",
        "--rm",
        "-i",
        "--init",
        "--name",
        container_name(execution_id),
        "--read-only",
        "--tmpfs",
        "/tmp:rw,size=256m",  # noqa: S108 - tmpfs inside the container
        "--tmpfs",
        f"{CONTAINER_HOME}:rw,size=256m,uid=1000,gid=1000",
        "--user",
        user,
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        settings.memory,
        "--cpus",
        str(settings.cpus),
        "--pids-limit",
        str(settings.pids_limit),
        "-e",
        f"HOME={CONTAINER_HOME}",
        "-e",
        settings.token_env,  # value inherited from the environment, never in argv
        "-v",
        f"{mount}:{CONTAINER_WORKDIR}",
        "-w",
        CONTAINER_WORKDIR,
        settings.image,
        *claude_args,
    ]
    if settings.disallowed_tools:
        args += ["--disallowedTools", *settings.disallowed_tools]
    return args


def container_environment(settings: AgentContainerSettings) -> dict[str, str]:
    """Minimal environment for the docker CLI: basics plus the single token."""
    env = {k: v for k, v in os.environ.items() if k in _DOCKER_ENV}
    token = os.environ.get(settings.token_env)
    if token:
        env[settings.token_env] = token
    if uses_wsl(settings):
        # WSL only forwards variables listed in WSLENV into the Linux side.
        env["WSLENV"] = settings.token_env + "/u"
    return env


def removal_args(settings: AgentContainerSettings, execution_id: str) -> list[str]:
    return [*settings.command, "rm", "-f", container_name(execution_id)]
