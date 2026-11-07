"""Command-based validation steps: tests, lint, type checking."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from agentbridge.config.settings import DockerSandboxSettings
from agentbridge.errors import PolicyViolationError
from agentbridge.execution.process import run_process
from agentbridge.execution.sandbox import docker_available, expand_for_container, wrap_command
from agentbridge.security.permissions import check_command
from agentbridge.security.policies import Policy
from agentbridge.security.secrets import safe_environment
from agentbridge.validation.models import Outcome, StepResult

_MISSING_TOOL = re.compile(r"No module named ([\w.]+)|not recognized|command not found")
_PYTEST_COUNTS = re.compile(r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)")


def validation_environment(cache_dir: Path | None) -> dict[str, str]:
    """Environment that keeps tool caches out of the task workspace."""
    env = safe_environment()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_ADDOPTS"] = (env.get("PYTEST_ADDOPTS", "") + " -p no:cacheprovider").strip()
    env["RUFF_NO_CACHE"] = "true"
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        env["MYPY_CACHE_DIR"] = str(cache_dir / "mypy")
    return env


def expand(command: list[str]) -> list[str]:
    return [sys.executable if part == "{python}" else part for part in command]


def parse_pytest_counts(output: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    # Use the last summary line only.
    summary_lines = [line for line in output.splitlines() if _PYTEST_COUNTS.search(line)]
    if not summary_lines:
        return counts
    for number, label in _PYTEST_COUNTS.findall(summary_lines[-1]):
        key = "errors" if label in ("error", "errors") else label
        counts[key] = counts.get(key, 0) + int(number)
    return counts


async def run_command_step(
    name: str,
    command: list[str],
    workdir: Path,
    policy: Policy,
    timeout: int,
    *,
    blocking: bool = True,
    cache_dir: Path | None = None,
    sandbox: DockerSandboxSettings | None = None,
) -> StepResult:
    args = expand_for_container(command) if sandbox else expand(command)
    try:
        check_command(args, policy)
    except PolicyViolationError as exc:
        return StepResult(
            name=name,
            outcome=Outcome.FAIL,
            command=args,
            summary=f"Blocked by policy: {exc.message}",
        )
    env = validation_environment(None if sandbox else cache_dir)
    run_args = args
    if sandbox is not None:
        if not docker_available(sandbox):
            # Fail closed: never fall back to running agent-written code on the host.
            return StepResult(
                name=name,
                outcome=Outcome.FAIL,
                command=args,
                summary="validation.sandbox is 'docker' but the docker CLI is not available",
            )
        run_args = wrap_command(args, workdir, sandbox, env)
    result = await run_process(run_args, cwd=workdir, timeout=timeout, env=env)
    output = (result.stdout + "\n" + result.stderr).strip()
    tail = output[-3000:]
    base = {
        "name": name,
        "command": args,
        "exit_code": result.exit_code,
        "duration_seconds": result.duration_seconds,
        "output_tail": tail,
    }
    if result.error:
        return StepResult(outcome=Outcome.WARNING, summary=f"Skipped: {result.error}", **base)
    if result.timed_out:
        return StepResult(outcome=Outcome.FAIL, summary=f"Timed out after {timeout}s", **base)
    missing = _MISSING_TOOL.search(output)
    if result.exit_code != 0 and missing and len(output) < 600:
        return StepResult(
            outcome=Outcome.WARNING,
            summary=f"Skipped: tool unavailable ({missing.group(0)})",
            **base,
        )
    if name == "tests":
        counts = parse_pytest_counts(output)
        details: dict[str, object] = dict(counts)
        if result.exit_code == 5:
            return StepResult(
                outcome=Outcome.WARNING, summary="No tests were collected", details=details, **base
            )
        outcome = Outcome.PASS if result.exit_code == 0 else Outcome.FAIL
        summary = ", ".join(f"{v} {k}" for k, v in counts.items()) or f"exit {result.exit_code}"
        return StepResult(outcome=outcome, summary=summary, details=details, **base)
    if result.exit_code == 0:
        return StepResult(outcome=Outcome.PASS, summary="OK", **base)
    lines = [line for line in output.splitlines() if line.strip()]
    summary = lines[-1][:300] if lines else f"exit {result.exit_code}"
    return StepResult(
        outcome=Outcome.FAIL if blocking else Outcome.WARNING, summary=summary, **base
    )
