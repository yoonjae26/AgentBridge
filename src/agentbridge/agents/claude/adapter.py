"""Claude Code CLI adapter.

Uses the documented non-interactive interface:
``claude -p --output-format json --permission-mode <mode>`` with the prompt on
stdin. Verified against Claude Code 2.1.x (see docs/provider-capabilities.md).
Permission bypass flags are never used.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agentbridge.agents.base import (
    AgentAdapter,
    AvailabilityReport,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
    UsageMetrics,
)
from agentbridge.agents.capabilities import Capability, OperationSupport, ProviderCapabilities
from agentbridge.agents.claude.container import (
    container_environment,
    docker_run_args,
    removal_args,
)
from agentbridge.config.settings import ProviderSettings
from agentbridge.execution.process import ProcessResult, resolve_executable, run_process
from agentbridge.security.secrets import redact, safe_environment


class ClaudeCodeAdapter(AgentAdapter):
    provider_type = "claude_code"

    def __init__(self, name: str, settings: ProviderSettings) -> None:
        super().__init__(name, settings)
        self.command = settings.command or "claude"

    async def check_availability(self) -> AvailabilityReport:
        container = self.settings.container
        if container.enabled:
            details = [
                f"Container mode: image {container.image}, docker command "
                f"{' '.join(container.command)}",
                "No host credentials or home directory are mounted.",
            ]
            docker = resolve_executable(container.command[0])
            if docker is None:
                return AvailabilityReport(
                    available=False, details=[*details, f"'{container.command[0]}' not found"]
                )
            if not os.environ.get(container.token_env):
                return AvailabilityReport(
                    available=False,
                    auth="missing",
                    details=[
                        *details,
                        f"{container.token_env} is not set. Create a token with "
                        "'claude setup-token' and store it in your user environment "
                        "(never in agentbridge.yaml).",
                    ],
                )
            return AvailabilityReport(
                available=True,
                executable=docker,
                auth="ok",
                details=[*details, f"{container.token_env} is set (value not inspected)"],
            )
        executable = resolve_executable(self.command)
        if executable is None:
            return AvailabilityReport(
                available=False,
                details=[
                    f"'{self.command}' not found on PATH",
                    "Install Claude Code: https://docs.anthropic.com/en/docs/claude-code",
                ],
            )
        result = await run_process(
            [executable, "--version"], cwd=Path.cwd(), timeout=60, env=safe_environment()
        )
        if not result.ok:
            return AvailabilityReport(
                available=False,
                executable=executable,
                details=[f"'{self.command} --version' failed: {result.error or result.stderr}"],
            )
        version = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        # We only check that credentials *exist*; we never read or print them.
        auth = "unknown"
        details = []
        if os.environ.get("ANTHROPIC_API_KEY"):
            auth = "ok"
            details.append("ANTHROPIC_API_KEY is set (value not inspected)")
        elif (Path.home() / ".claude" / ".credentials.json").exists():
            auth = "ok"
            details.append("Claude Code login credentials found (validity not verified)")
        else:
            details.append(
                "No API key or credentials file detected; the CLI may still be logged in "
                "via the OS keychain. Run 'claude' once interactively to log in."
            )
        return AvailabilityReport(
            available=True, version=version, executable=executable, auth=auth, details=details
        )

    async def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_type=self.provider_type,
            capabilities=frozenset(
                {
                    Capability.PLAN,
                    Capability.EDIT_CODE,
                    Capability.ANALYZE,
                    Capability.REVIEW,
                    Capability.LOCAL_WORKSPACE,
                    Capability.STRUCTURED_OUTPUT,
                    Capability.CANCEL,
                    Capability.COST_REPORTING,
                    Capability.TOKEN_REPORTING,
                }
            ),
            cancellation=OperationSupport.SUPPORTED,
            status_query=OperationSupport.UNSUPPORTED,
            notes=[
                "Cancellation terminates the local CLI process tree.",
                "Execution status cannot be recovered after an AgentBridge restart.",
                "total_cost_usd is a CLI-computed estimate, not billing data.",
            ],
        )

    def build_args(self, executable: str, request: ExecutionRequest) -> list[str]:
        mode = request.permission_mode or self.settings.permission_mode or "acceptEdits"
        if not request.agents_may_edit:
            mode = "plan"
        args = [executable, "-p", "--output-format", "json", "--permission-mode", mode]
        if self.settings.model:
            args += ["--model", self.settings.model]
        if self.settings.allowed_tools:
            args += ["--allowedTools", *self.settings.allowed_tools]
        args += list(self.settings.extra_args)
        return args

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        if self.settings.container.enabled:
            return await self._execute_in_container(request)
        executable = resolve_executable(self.command)
        if executable is None:
            return ExecutionResult(
                execution_id=request.execution_id,
                provider=self.name,
                state=ExecutionState.UNAVAILABLE,
                error=f"'{self.command}' not found on PATH",
                retryable=False,
            )
        if request.workdir is None:
            raise ValueError("Claude Code adapter requires a local working directory")
        cancel = self._cancel_event(request.execution_id)
        args = self.build_args(executable, request)
        try:
            process = await run_process(
                args,
                cwd=request.workdir,
                timeout=request.timeout_seconds,
                env=safe_environment(),
                stdin_data=request.prompt,
                cancel_event=cancel,
            )
        finally:
            self._forget(request.execution_id)
        return self.parse_result(request, process)

    async def _execute_in_container(self, request: ExecutionRequest) -> ExecutionResult:
        container = self.settings.container
        if request.workdir is None:
            raise ValueError("Claude Code adapter requires a local working directory")
        if resolve_executable(container.command[0]) is None or not os.environ.get(
            container.token_env
        ):
            # Fail closed: never fall back to the host or to mounting credentials.
            return ExecutionResult(
                execution_id=request.execution_id,
                provider=self.name,
                state=ExecutionState.UNAVAILABLE,
                error=f"Container mode needs '{container.command[0]}' and "
                f"{container.token_env}; see 'agentbridge providers check'",
            )
        args = docker_run_args(
            container, request.workdir, request.execution_id, self.build_args("claude", request)
        )
        env = container_environment(container)
        cancel = self._cancel_event(request.execution_id)
        try:
            process = await run_process(
                args,
                cwd=request.workdir,
                timeout=request.timeout_seconds,
                env=env,
                stdin_data=request.prompt,
                cancel_event=cancel,
            )
        finally:
            self._forget(request.execution_id)
            # Killing the docker client does not always stop the container itself.
            await run_process(
                removal_args(container, request.execution_id),
                cwd=request.workdir,
                timeout=60,
                env=env,
            )
        result = self.parse_result(request, process)
        result.metadata["isolation"] = f"container:{container.image}"
        return result

    def parse_result(self, request: ExecutionRequest, process: ProcessResult) -> ExecutionResult:
        request.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = request.output_dir / f"{request.execution_id}.claude.json"
        output_path.write_text(
            process.stdout + ("\n--- stderr ---\n" + process.stderr if process.stderr else ""),
            encoding="utf-8",
        )
        base: dict[str, Any] = {
            "execution_id": request.execution_id,
            "provider": self.name,
            "exit_code": process.exit_code,
            "duration_seconds": process.duration_seconds,
            "output_path": str(output_path),
            "metadata": {
                "command": [
                    Path(args).name if i == 0 else args for i, args in enumerate(process.args[:6])
                ]
            },
        }
        if process.error:
            return ExecutionResult(state=ExecutionState.FAILED, error=process.error, **base)
        if process.cancelled:
            return ExecutionResult(state=ExecutionState.CANCELLED, error="Cancelled", **base)
        if process.timed_out:
            return ExecutionResult(
                state=ExecutionState.TIMED_OUT,
                error=f"Timed out after {request.timeout_seconds}s",
                retryable=True,
                **base,
            )
        payload = _parse_json_output(process.stdout)
        if payload is None:
            state = ExecutionState.FAILED if process.exit_code else ExecutionState.INVALID_OUTPUT
            return ExecutionResult(
                state=state,
                error=redact(
                    (process.stderr.strip() or process.stdout.strip() or "no output")[-2000:]
                ),
                retryable=bool(process.exit_code),
                **base,
            )
        usage = _usage_from_payload(payload)
        text = str(payload.get("result") or "")
        base["metadata"].update(
            {
                "session_id": payload.get("session_id"),
                "num_turns": payload.get("num_turns"),
                "subtype": payload.get("subtype"),
                "provider_duration_ms": payload.get("duration_ms"),
            }
        )
        if payload.get("is_error") or process.exit_code:
            return ExecutionResult(
                state=ExecutionState.FAILED,
                summary=redact(text[-4000:]),
                error=redact(text[-2000:] or process.stderr[-2000:] or "Claude reported an error"),
                usage=usage,
                retryable=True,
                **base,
            )
        return ExecutionResult(
            state=ExecutionState.COMPLETED, summary=redact(text[-8000:]), usage=usage, **base
        )


def _parse_json_output(stdout: str) -> dict[str, Any] | None:
    text = stdout.strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Some versions may print warnings before the JSON object; use the last line.
        for line in reversed(text.splitlines()):
            try:
                data = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
        else:
            return None
    if isinstance(data, list):  # stream-style arrays: take the final result object
        results = [item for item in data if isinstance(item, dict) and item.get("type") == "result"]
        data = results[-1] if results else None
    return data if isinstance(data, dict) else None


def _usage_from_payload(payload: dict[str, Any]) -> UsageMetrics:
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
    input_tokens = output_tokens = None
    if usage:
        parts = [
            usage.get(key)
            for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
        ]
        numeric = [p for p in parts if isinstance(p, int)]
        input_tokens = sum(numeric) if numeric else None
        output_tokens = (
            usage.get("output_tokens") if isinstance(usage.get("output_tokens"), int) else None
        )
    cost = payload.get("total_cost_usd")
    model_usage = payload.get("modelUsage")
    model = next(iter(model_usage), None) if isinstance(model_usage, dict) else None
    return UsageMetrics(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=float(cost) if isinstance(cost, int | float) else None,
        cost_kind="estimated" if isinstance(cost, int | float) else None,
        cost_source="claude_cli:total_cost_usd" if isinstance(cost, int | float) else None,
    )
