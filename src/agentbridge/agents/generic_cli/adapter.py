"""Generic CLI adapter for other coding agents (e.g. Codex, OpenCode).

The user declares the command, an argument template and the capabilities the
tool really has. Placeholders: ``{prompt_file}`` (path to a file holding the
prompt) and ``{workdir}``. If neither appears, the prompt is sent on stdin.
"""

from __future__ import annotations

import time
from pathlib import Path

from agentbridge.agents.base import (
    AgentAdapter,
    AvailabilityReport,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
)
from agentbridge.agents.capabilities import Capability, OperationSupport, ProviderCapabilities
from agentbridge.execution.process import resolve_executable, run_process
from agentbridge.security.secrets import safe_environment


class GenericCliAdapter(AgentAdapter):
    provider_type = "generic_cli"

    async def check_availability(self) -> AvailabilityReport:
        command = self.settings.command or ""
        executable = resolve_executable(command)
        if executable is None:
            return AvailabilityReport(available=False, details=[f"'{command}' not found on PATH"])
        return AvailabilityReport(
            available=True,
            executable=executable,
            details=["Capabilities are user-declared and not verified by AgentBridge."],
        )

    async def get_capabilities(self) -> ProviderCapabilities:
        declared = set()
        for item in self.settings.capabilities:
            declared.add(Capability(item))
        declared |= {Capability.LOCAL_WORKSPACE, Capability.CANCEL}
        return ProviderCapabilities(
            provider_type=self.provider_type,
            capabilities=frozenset(declared),
            cancellation=OperationSupport.SUPPORTED,
            status_query=OperationSupport.UNSUPPORTED,
            notes=["User-declared capabilities."],
        )

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        started = time.monotonic()
        executable = resolve_executable(self.settings.command or "")
        if executable is None or request.workdir is None:
            return ExecutionResult(
                execution_id=request.execution_id,
                provider=self.name,
                state=ExecutionState.UNAVAILABLE,
                error="Executable or working directory missing",
            )
        request.output_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = request.output_dir / f"{request.execution_id}.prompt.txt"
        prompt_file.write_text(request.prompt, encoding="utf-8")
        uses_file = any("{prompt_file}" in a for a in self.settings.args)
        args = [executable] + [
            a.replace("{prompt_file}", str(prompt_file)).replace("{workdir}", str(request.workdir))
            for a in self.settings.args
        ]
        cancel = self._cancel_event(request.execution_id)
        try:
            process = await run_process(
                args,
                cwd=request.workdir,
                timeout=request.timeout_seconds,
                env=safe_environment(),
                stdin_data=None if uses_file else request.prompt,
                cancel_event=cancel,
            )
        finally:
            self._forget(request.execution_id)
        output_path = request.output_dir / f"{request.execution_id}.out.txt"
        output_path.write_text(
            process.stdout + "\n--- stderr ---\n" + process.stderr, encoding="utf-8"
        )
        if process.cancelled:
            state = ExecutionState.CANCELLED
        elif process.timed_out:
            state = ExecutionState.TIMED_OUT
        elif process.ok:
            state = ExecutionState.COMPLETED
        else:
            state = ExecutionState.FAILED
        return ExecutionResult(
            execution_id=request.execution_id,
            provider=self.name,
            state=state,
            summary=process.stdout.strip()[-4000:],
            exit_code=process.exit_code,
            duration_seconds=round(time.monotonic() - started, 3),
            output_path=str(Path(output_path)),
            error=process.error or (process.stderr.strip()[-2000:] if not process.ok else None),
            retryable=state in (ExecutionState.FAILED, ExecutionState.TIMED_OUT),
        )
