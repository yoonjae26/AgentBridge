"""Validation result schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class Outcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NEEDS_HUMAN_REVIEW = "NEEDS_HUMAN_REVIEW"
    SKIPPED = "SKIPPED"


class StepResult(BaseModel):
    name: str
    outcome: Outcome
    summary: str = ""
    command: list[str] | None = None
    exit_code: int | None = None
    duration_seconds: float | None = None
    output_tail: str = ""
    details: dict[str, object] = Field(default_factory=dict)


class ValidationReport(BaseModel):
    outcome: Outcome
    steps: list[StepResult]
    changed_files: list[str] = Field(default_factory=list)
    base_commit: str | None = None
    head_commit: str | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    started_at: str
    finished_at: str

    def step(self, name: str) -> StepResult | None:
        return next((s for s in self.steps if s.name == name), None)


def aggregate(steps: list[StepResult]) -> Outcome:
    outcomes = {s.outcome for s in steps}
    if Outcome.FAIL in outcomes:
        return Outcome.FAIL
    if Outcome.NEEDS_HUMAN_REVIEW in outcomes:
        return Outcome.NEEDS_HUMAN_REVIEW
    if Outcome.WARNING in outcomes:
        return Outcome.WARNING
    return Outcome.PASS
