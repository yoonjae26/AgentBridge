"""AgentBench schemas."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentbridge.config.settings import ProviderSettings, RoutingSettings


class TaskCategory(StrEnum):
    BUG_FIXING = "bug_fixing"
    FEATURE = "feature_implementation"
    REFACTORING = "refactoring"
    TEST_GENERATION = "unit_test_generation"
    DOCUMENTATION = "documentation_generation"
    CODE_REVIEW = "code_review"
    DEPENDENCY_UPDATE = "dependency_updates"
    REPOSITORY_ANALYSIS = "repository_analysis"


class BenchmarkTask(BaseModel):
    """One benchmark task (``benchmarks/tasks/<task_id>/task.yaml``)."""

    model_config = ConfigDict(extra="forbid")

    task_id: str
    repository: str = "fixture"  # "fixture" = the task's own repo/ directory
    base_commit: str | None = None  # null for fixtures: commit is synthesised (see docs)
    issue_description: str
    task_category: TaskCategory
    acceptance_criteria: list[str] = Field(min_length=1)
    setup_commands: list[list[str]] = Field(default_factory=list)
    test_commands: list[list[str]] = Field(min_length=1)
    regression_test_command: list[str] | None = None
    timeout: int = Field(default=900, ge=10, le=86_400)
    difficulty: Literal["easy", "medium", "hard"]
    expected_files: list[str] = Field(default_factory=list)
    license: str = "MIT (authored for AgentBench)"

    @field_validator("task_id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,39}", value):
            raise ValueError("task_id must be lowercase alphanumeric with dashes")
        return value


class BenchConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""
    description: str
    kind: Literal["control", "single_agent", "multi_agent", "remote"] = "single_agent"
    planner_mode: Literal["single", "standard", "provider"] = "single"
    providers: dict[str, ProviderSettings]
    routing: RoutingSettings
    oracle: bool = False  # mock writes the reference solution (harness sanity check)


class ExperimentRecord(BaseModel):
    """Raw result of one (task, configuration, repetition). Missing data is null."""

    experiment_id: str
    task_id: str
    configuration: str
    repetition: int
    status: Literal["completed", "failed", "error", "not_executable"]
    status_reason: str | None = None
    test_passed: bool | None = None
    hidden_tests_passed: int | None = None
    hidden_tests_failed: int | None = None
    execution_time_seconds: float | None = None
    token_usage: dict[str, int | None] | None = None
    measured_cost: float | None = None
    estimated_cost: float | None = None
    estimated_cost_source: str | None = None
    human_interventions: int | None = None
    regression_detected: bool | None = None
    regressed_tests: list[str] = Field(default_factory=list)
    retries: int | None = None
    merge_success: bool | None = None
    validation_outcome: str | None = None
    agentbridge_task_statuses: dict[str, str] = Field(default_factory=dict)
    base_commit: str | None = None
    fixture_digest: str | None = None
    providers: dict[str, Any] = Field(default_factory=dict)
    started_at: str
    finished_at: str
    artifacts_dir: str | None = None
