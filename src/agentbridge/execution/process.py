"""Asynchronous subprocess execution with timeouts and cancellation.

Commands are always executed from argument lists, never through a shell.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentbridge.security.secrets import redact

MAX_CAPTURE_BYTES = 4 * 1024 * 1024


@dataclass
class ProcessResult:
    args: list[str]
    exit_code: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    cancelled: bool = False
    error: str | None = None
    truncated: bool = False
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out and not self.cancelled and not self.error


def resolve_executable(name: str) -> str | None:
    """Return an absolute path for ``name`` or None if not installed."""
    if os.path.isabs(name):
        return name if os.path.exists(name) else None
    return shutil.which(name)


def _kill_tree(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    if sys.platform == "win32":
        # taskkill /T terminates the whole tree (agents spawn child processes).
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
    else:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        process.kill()


def _decode(data: bytes) -> tuple[str, bool]:
    truncated = len(data) > MAX_CAPTURE_BYTES
    if truncated:
        data = data[-MAX_CAPTURE_BYTES:]
    return data.decode("utf-8", errors="replace"), truncated


async def run_process(
    args: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: Mapping[str, str] | None = None,
    stdin_data: str | None = None,
    cancel_event: asyncio.Event | None = None,
    redact_output: bool = True,
) -> ProcessResult:
    """Run ``args`` in ``cwd`` with a hard timeout and optional cancellation."""
    started = time.monotonic()
    executable = resolve_executable(args[0])
    if executable is None:
        return ProcessResult(
            args=args,
            exit_code=None,
            stdout="",
            stderr="",
            duration_seconds=0.0,
            error=f"Executable not found: {args[0]}",
        )
    kwargs: dict[str, object] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    try:
        process = await asyncio.create_subprocess_exec(
            executable,
            *args[1:],
            cwd=str(cwd),
            env=dict(env) if env is not None else None,
            stdin=asyncio.subprocess.PIPE if stdin_data is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,  # type: ignore[arg-type]
        )
    except OSError as exc:
        return ProcessResult(
            args=args,
            exit_code=None,
            stdout="",
            stderr="",
            duration_seconds=time.monotonic() - started,
            error=f"Failed to start {args[0]}: {exc}",
        )

    input_bytes = stdin_data.encode("utf-8") if stdin_data is not None else None
    communicate = asyncio.ensure_future(process.communicate(input_bytes))
    waiters: set[asyncio.Future[Any]] = {communicate}
    cancel_waiter: asyncio.Future[Any] | None = None
    if cancel_event is not None:
        cancel_waiter = asyncio.ensure_future(cancel_event.wait())
        waiters.add(cancel_waiter)

    timed_out = cancelled = False
    try:
        done, _ = await asyncio.wait(waiters, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if communicate not in done:
            if cancel_waiter is not None and cancel_waiter in done:
                cancelled = True
            else:
                timed_out = True
            _kill_tree(process)
    except asyncio.CancelledError:
        _kill_tree(process)
        raise
    finally:
        if cancel_waiter is not None and not cancel_waiter.done():
            cancel_waiter.cancel()

    try:
        stdout_b, stderr_b = await asyncio.wait_for(communicate, timeout=15)
    except (TimeoutError, asyncio.CancelledError):
        stdout_b, stderr_b = b"", b""
    stdout, t1 = _decode(stdout_b or b"")
    stderr, t2 = _decode(stderr_b or b"")
    if redact_output:
        stdout, stderr = redact(stdout), redact(stderr)
    return ProcessResult(
        args=args,
        exit_code=process.returncode if not (timed_out or cancelled) else None,
        stdout=stdout,
        stderr=stderr,
        duration_seconds=round(time.monotonic() - started, 3),
        timed_out=timed_out,
        cancelled=cancelled,
        truncated=t1 or t2,
    )
