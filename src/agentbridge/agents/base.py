"""Provider-independent agent adapter contract."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from agentbridge.agents.capabilities import ProviderCapabilities
from agentbridge.config.settings import ProviderSettings


class ExecutionState(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    INVALID_OUTPUT = "invalid_output"
    UNAVAILABLE = "unavailable"
    HANDOFF_PREPARED = "handoff_prepared"  # nothing executed; a human must act
    RUNNING = "running"
    UNKNOWN = "unknown"


class UnsupportedOperationError(Exception):
    """Raised when an adapter is asked for an operation it does not support."""


class AvailabilityReport(BaseModel):
    available: bool
    version: str | None = None
    executable: str | None = None
    auth: Literal["ok", "missing", "unknown", "not_required"] = "unknown"
    details: list[str] = Field(default_factory=list)


class UsageMetrics(BaseModel):
    """Usage data. ``None`` means *unavailable*, never zero."""

    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    # "measured" (billing data) vs "estimated" (e.g. CLI-computed figure).
    cost_kind: Literal["measured", "estimated"] | None = None
    cost_source: str | None = None


class ExecutionRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str
    execution_id: str
    attempt: int = 1
    title: str
    description: str = ""
    role: str
    prompt: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    expected_files: list[str] = Field(default_factory=list)
    workdir: Path | None = None
    output_dir: Path
    timeout_seconds: int
    agents_may_edit: bool = True
    permission_mode: str | None = None
    repository_info: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(BaseModel):
    execution_id: str
    provider: str
    state: ExecutionState
    summary: str = ""
    exit_code: int | None = None
    duration_seconds: float | None = None
    output_path: str | None = None
    error: str | None = None
    retryable: bool = False
    usage: UsageMetrics = Field(default_factory=UsageMetrics)
    structured_output: dict[str, Any] | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentAdapter(ABC):
    """Contract every provider adapter implements.

    Unsupported operations raise ``UnsupportedOperationError`` (and are declared
    as such in ``get_capabilities``); adapters must never fake support.
    """

    provider_type: str = "abstract"

    def __init__(self, name: str, settings: ProviderSettings) -> None:
        self.name = name
        self.settings = settings
        self._cancel_events: dict[str, asyncio.Event] = {}

    @abstractmethod
    async def check_availability(self) -> AvailabilityReport: ...

    @abstractmethod
    async def get_capabilities(self) -> ProviderCapabilities: ...

    @abstractmethod
    async def execute(self, request: ExecutionRequest) -> ExecutionResult: ...

    async def get_status(self, execution_id: str) -> ExecutionState:
        """Status of an execution, possibly from a previous process.

        The default is honest: without provider support the state is UNKNOWN.
        """
        return ExecutionState.UNKNOWN

    async def cancel(self, execution_id: str) -> bool:
        """Request cancellation. Returns True if a running execution was signalled."""
        event = self._cancel_events.get(execution_id)
        if event is None:
            return False
        event.set()
        return True

    # Helpers for subclasses ------------------------------------------------
    def _cancel_event(self, execution_id: str) -> asyncio.Event:
        event = self._cancel_events.get(execution_id)
        if event is None:
            event = asyncio.Event()
            self._cancel_events[execution_id] = event
        return event

    def _forget(self, execution_id: str) -> None:
        self._cancel_events.pop(execution_id, None)
