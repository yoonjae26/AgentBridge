"""Validation pipeline. Agent claims of success are never trusted."""

from __future__ import annotations

from pathlib import Path

from agentbridge.config.settings import ValidationSettings
from agentbridge.security.policies import Policy
from agentbridge.storage.database import utcnow
from agentbridge.validation.models import Outcome, StepResult, ValidationReport, aggregate
from agentbridge.validation.review import Finding, review_diff
from agentbridge.validation.runners import run_command_step
from agentbridge.workspace.diff import DiffSummary, compute_diff


def _scope_step(diff: DiffSummary, expected: list[str], max_files: int) -> StepResult:
    if len(diff.files) > max_files:
        return StepResult(
            name="scope",
            outcome=Outcome.NEEDS_HUMAN_REVIEW,
            summary=f"{len(diff.files)} files changed (limit {max_files})",
        )
    if not expected:
        return StepResult(name="scope", outcome=Outcome.PASS, summary="No declared scope")

    def allowed(path: str) -> bool:
        for pattern in expected:
            base = pattern.rstrip("*").rstrip("/")
            if path == base or path.startswith(base + "/"):
                return True
        return False

    outside = [p for p in diff.paths if not allowed(p)]
    if outside:
        return StepResult(
            name="scope",
            outcome=Outcome.NEEDS_HUMAN_REVIEW,
            summary=f"{len(outside)} file(s) outside declared scope",
            details={"outside_scope": outside},
        )
    return StepResult(name="scope", outcome=Outcome.PASS, summary="All changes within scope")


def _review_step(findings: list[Finding]) -> StepResult:
    data = [f.__dict__ for f in findings]
    severities = {f.severity for f in findings}
    if "critical" in severities:
        outcome = Outcome.FAIL
    elif "high" in severities:
        outcome = Outcome.NEEDS_HUMAN_REVIEW
    elif findings:
        outcome = Outcome.WARNING
    else:
        outcome = Outcome.PASS
    summary = f"{len(findings)} finding(s)" if findings else "No findings"
    return StepResult(name="review", outcome=outcome, summary=summary, details={"findings": data})


class ValidationEngine:
    def __init__(
        self, settings: ValidationSettings, policy: Policy, cache_dir: Path | None = None
    ) -> None:
        self.settings = settings
        self.policy = policy
        self.cache_dir = cache_dir
        self._sandbox = settings.docker if settings.sandbox == "docker" else None

    async def validate(
        self,
        workdir: Path,
        base_commit: str,
        *,
        expected_files: list[str] | None = None,
        expect_changes: bool = True,
        extra_steps: list[StepResult] | None = None,
    ) -> ValidationReport:
        started = utcnow()
        steps: list[StepResult] = []
        diff = compute_diff(workdir, base_commit)
        if diff.is_empty:
            steps.append(
                StepResult(
                    name="diff",
                    outcome=Outcome.WARNING if expect_changes else Outcome.PASS,
                    summary="No file changes",
                )
            )
        else:
            steps.append(
                StepResult(
                    name="diff",
                    outcome=Outcome.PASS,
                    summary=f"{len(diff.files)} file(s) changed",
                    details={"files": [f.model_dump() for f in diff.files]},
                )
            )
        steps.append(_scope_step(diff, expected_files or [], self.settings.max_changed_files))
        steps.extend(extra_steps or [])
        timeout = self.settings.command_timeout_seconds
        if self.settings.run_lint:
            steps.append(
                await run_command_step(
                    "lint",
                    self.settings.lint_command,
                    workdir,
                    self.policy,
                    timeout,
                    blocking=self.settings.lint_blocking,
                    cache_dir=self.cache_dir,
                    sandbox=self._sandbox,
                )
            )
        if self.settings.run_type_check:
            steps.append(
                await run_command_step(
                    "type_check",
                    self.settings.type_check_command,
                    workdir,
                    self.policy,
                    timeout,
                    blocking=self.settings.type_check_blocking,
                    cache_dir=self.cache_dir,
                    sandbox=self._sandbox,
                )
            )
        if self.settings.run_tests:
            steps.append(
                await run_command_step(
                    "tests",
                    self.settings.test_command,
                    workdir,
                    self.policy,
                    timeout,
                    cache_dir=self.cache_dir,
                    sandbox=self._sandbox,
                )
            )
        steps.append(_review_step(review_diff(diff)))
        tests = next((s for s in steps if s.name == "tests"), None)
        passed = failed = None
        if tests is not None and tests.outcome in (Outcome.PASS, Outcome.FAIL):
            counts = {k: v for k, v in tests.details.items() if isinstance(v, int)}
            passed = counts.get("passed", 0)
            failed = counts.get("failed", 0) + counts.get("errors", 0)
        return ValidationReport(
            outcome=aggregate(steps),
            steps=steps,
            changed_files=diff.paths,
            base_commit=base_commit,
            head_commit=diff.head,
            tests_passed=passed,
            tests_failed=failed,
            started_at=started,
            finished_at=utcnow(),
        )
