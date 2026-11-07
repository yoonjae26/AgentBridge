"""Task and plan schemas."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentbridge.agents.capabilities import Capability
from agentbridge.errors import PolicyViolationError
from agentbridge.security.paths import validate_relative_path


class TaskStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    VALIDATING = "VALIDATING"
    INTEGRATING = "INTEGRATING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"


TERMINAL_STATUSES = frozenset({TaskStatus.SUCCEEDED, TaskStatus.CANCELLED})
# States in which an AgentBridge process is (or was) actively doing work.
ACTIVE_STATUSES = frozenset(
    {TaskStatus.QUEUED, TaskStatus.RUNNING, TaskStatus.VALIDATING, TaskStatus.INTEGRATING}
)


class TaskRole(StrEnum):
    PLANNER = "planner"
    ANALYST = "analyst"
    DEVELOPER = "developer"
    TESTER = "tester"
    DOCUMENTER = "documenter"
    REVIEWER = "reviewer"


ROLE_CAPABILITIES: dict[TaskRole, frozenset[Capability]] = {
    TaskRole.PLANNER: frozenset({Capability.PLAN}),
    TaskRole.ANALYST: frozenset({Capability.ANALYZE}),
    TaskRole.DEVELOPER: frozenset({Capability.EDIT_CODE}),
    TaskRole.TESTER: frozenset({Capability.EDIT_CODE}),
    TaskRole.DOCUMENTER: frozenset({Capability.EDIT_CODE}),
    TaskRole.REVIEWER: frozenset({Capability.REVIEW}),
}

# Roles whose output is expected to modify files.
EDITING_ROLES = frozenset({TaskRole.DEVELOPER, TaskRole.TESTER, TaskRole.DOCUMENTER})


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WaitingReason(StrEnum):
    MERGE_APPROVAL = "merge_approval"
    REMOTE_HANDOFF = "remote_handoff"
    HUMAN_REVIEW = "human_review"


_TASK_KEY = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


class TaskSpec(BaseModel):
    """A planned unit of work, as produced (and validated) from planner output."""

    model_config = ConfigDict(extra="forbid")

    id: str
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20_000)
    role: TaskRole = TaskRole.DEVELOPER
    dependencies: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    expected_files: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.LOW
    timeout_seconds: int | None = Field(default=None, ge=1, le=86_400)
    required_capabilities: list[Capability] = Field(default_factory=list)
    priority: int = Field(default=0, ge=0, le=100)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _TASK_KEY.match(value):
            raise ValueError("task id must be lowercase alphanumeric with dashes (max 40)")
        return value

    @field_validator("expected_files")
    @classmethod
    def _safe_paths(cls, value: list[str]) -> list[str]:
        cleaned = []
        for item in value:
            # Allow simple glob suffixes ("src/*") but validate the path part.
            try:
                cleaned.append(validate_relative_path(item))
            except PolicyViolationError as exc:
                raise ValueError(exc.message) from exc
        return cleaned

    def effective_capabilities(self) -> frozenset[Capability]:
        return ROLE_CAPABILITIES[self.role] | frozenset(self.required_capabilities)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    objective: str = Field(min_length=1, max_length=20_000)
    tasks: list[TaskSpec] = Field(min_length=1, max_length=50)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _graph_is_valid(self) -> Plan:
        # Imported here to avoid a circular import at module load time.
        from agentbridge.tasks.dependencies import validate_graph

        self.warnings = sorted(set(self.warnings) | set(validate_graph(self.tasks)))
        return self
