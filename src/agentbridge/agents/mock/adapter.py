"""Deterministic mock provider for development, tests and CI.

Scenarios: success, failure, delay, interrupt, invalid_output, unavailable.
The scenario comes from configuration and may be overridden per execution via
``request.metadata["mock_scenario"]``. Files written on success come from
``settings.files`` or ``request.metadata["mock_files"]``.
"""

from __future__ import annotations

import asyncio
import json
import time

from agentbridge.agents.base import (
    AgentAdapter,
    AvailabilityReport,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
)
from agentbridge.agents.capabilities import Capability, OperationSupport, ProviderCapabilities
from agentbridge.config.settings import ProviderSettings
from agentbridge.security.paths import resolve_inside


class MockAdapter(AgentAdapter):
    provider_type = "mock"

    def __init__(self, name: str, settings: ProviderSettings) -> None:
        super().__init__(name, settings)
        self._states: dict[str, ExecutionState] = {}

    async def check_availability(self) -> AvailabilityReport:
        if self.settings.scenario == "unavailable":
            return AvailabilityReport(
                available=False,
                auth="not_required",
                details=["mock scenario 'unavailable' simulates a missing provider"],
            )
        return AvailabilityReport(
            available=True,
            version="builtin",
            auth="not_required",
            details=[f"scenario={self.settings.scenario}"],
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
                    Capability.STATUS,
                }
            ),
            cancellation=OperationSupport.SUPPORTED,
            status_query=OperationSupport.SUPPORTED,
            notes=["Simulated provider; performs no AI work and costs nothing."],
        )

    async def get_status(self, execution_id: str) -> ExecutionState:
        return self._states.get(execution_id, ExecutionState.UNKNOWN)

    def _result(
        self, request: ExecutionRequest, state: ExecutionState, started: float, **kw: object
    ) -> ExecutionResult:
        self._states[request.execution_id] = state
        self._forget(request.execution_id)
        output = str(kw.pop("raw_output", kw.get("summary", "")))
        request.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = request.output_dir / f"{request.execution_id}.out.txt"
        output_path.write_text(output, encoding="utf-8")
        return ExecutionResult(
            execution_id=request.execution_id,
            provider=self.name,
            state=state,
            duration_seconds=round(time.monotonic() - started, 3),
            output_path=str(output_path),
            metadata={
                "mock_scenario": request.metadata.get("mock_scenario") or self.settings.scenario
            },
            **kw,
        )

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        started = time.monotonic()
        scenario = str(request.metadata.get("mock_scenario") or self.settings.scenario)
        cancel = self._cancel_event(request.execution_id)
        self._states[request.execution_id] = ExecutionState.RUNNING

        if scenario == "unavailable":
            return self._result(
                request,
                ExecutionState.UNAVAILABLE,
                started,
                error="Mock provider is unavailable (simulated)",
                retryable=True,
            )
        if scenario == "delay":
            delay = float(request.metadata.get("mock_delay_seconds", self.settings.delay_seconds))
            try:
                await asyncio.wait_for(cancel.wait(), timeout=min(delay, request.timeout_seconds))
                return self._result(
                    request,
                    ExecutionState.CANCELLED,
                    started,
                    error="Cancelled during simulated delay",
                )
            except TimeoutError:
                if delay >= request.timeout_seconds:
                    return self._result(
                        request,
                        ExecutionState.TIMED_OUT,
                        started,
                        error="Simulated execution exceeded timeout",
                        retryable=True,
                    )
        if scenario == "failure":
            return self._result(
                request,
                ExecutionState.FAILED,
                started,
                exit_code=1,
                error="Simulated provider failure",
                retryable=True,
                raw_output="mock: simulated failure",
            )
        if scenario == "interrupt":
            return self._result(
                request,
                ExecutionState.INTERRUPTED,
                started,
                error="Simulated interruption (process lost mid-execution)",
            )
        if scenario == "invalid_output":
            return self._result(
                request,
                ExecutionState.INVALID_OUTPUT,
                started,
                exit_code=0,
                error="Provider output could not be parsed",
                raw_output="\x00{not json",
            )

        # success (or delay that completed)
        structured: dict[str, object] | None = None
        if request.role == "planner":
            structured = self._plan(request)
            summary = f"Mock plan with {len(structured['tasks'])} task(s)"  # type: ignore[arg-type]
        elif request.role == "reviewer":
            summary = "VERDICT: PASS\nMock review: no findings (simulated, not a real review)."
        elif request.workdir is not None and request.agents_may_edit:
            files = dict(self.settings.files)
            files.update(request.metadata.get("mock_files") or {})
            if not files:
                files = {
                    f"mock_outputs/{request.task_id}.md": (
                        f"# Mock result for {request.task_id}\n\n"
                        f"Task: {request.title}\n\nThis file was written by the mock provider.\n"
                    )
                }
            for relative, content in files.items():
                target = resolve_inside(request.workdir, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
            summary = f"Mock provider wrote {len(files)} file(s): {', '.join(sorted(files))}"
        else:
            summary = "Mock analysis complete (simulated)."
        return self._result(
            request,
            ExecutionState.COMPLETED,
            started,
            exit_code=0,
            summary=summary,
            structured_output=structured,
            raw_output=json.dumps({"summary": summary, "structured": structured}),
        )

    @staticmethod
    def _plan(request: ExecutionRequest) -> dict[str, object]:
        objective = request.metadata.get("objective", request.title)
        return {
            "objective": objective,
            "tasks": [
                {
                    "id": "task-001",
                    "title": "Analyze repository",
                    "role": "analyst",
                    "dependencies": [],
                    "acceptance_criteria": ["Analysis summary exists"],
                },
                {
                    "id": "task-002",
                    "title": f"Implement: {objective}"[:200],
                    "description": str(objective),
                    "role": "developer",
                    "dependencies": ["task-001"],
                    "acceptance_criteria": ["Changes implement the objective", "Checks pass"],
                },
                {
                    "id": "task-003",
                    "title": "Review and validate implementation",
                    "role": "reviewer",
                    "dependencies": ["task-002"],
                    "acceptance_criteria": ["Review verdict recorded"],
                },
            ],
        }
