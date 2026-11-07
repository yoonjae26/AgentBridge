"""The orchestrator: plan -> schedule -> execute -> validate -> await approval."""

from __future__ import annotations

import asyncio
import contextlib
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentbridge.agents.base import (
    AgentAdapter,
    ExecutionRequest,
    ExecutionResult,
    ExecutionState,
)
from agentbridge.agents.capabilities import Capability
from agentbridge.agents.prompts import task_prompt
from agentbridge.agents.registry import AgentRegistry
from agentbridge.config.loader import ProjectPaths
from agentbridge.config.settings import PolicyProfile, Settings
from agentbridge.core.events import EventCallback, EventRecorder
from agentbridge.core.planner import provider_plan, single_plan, standard_plan
from agentbridge.core.router import Router
from agentbridge.errors import (
    AgentBridgeError,
    GitError,
    InvalidStateError,
    PolicyViolationError,
)
from agentbridge.reporting.generator import write_run_report, write_task_report
from agentbridge.security.policies import Policy, build_policy
from agentbridge.storage.database import ExecutionRecord, RunRecord, TaskRecord, utcnow
from agentbridge.storage.repositories import Store
from agentbridge.tasks.models import (
    ACTIVE_STATUSES,
    EDITING_ROLES,
    Plan,
    TaskRole,
    TaskSpec,
    TaskStatus,
    WaitingReason,
)
from agentbridge.tasks.recovery import recover_stale_tasks
from agentbridge.validation.engine import ValidationEngine
from agentbridge.validation.models import Outcome, StepResult, ValidationReport, aggregate
from agentbridge.workspace.git import Git
from agentbridge.workspace.integration import merge_branch
from agentbridge.workspace.manager import Workspace, WorkspaceManager, without_tool_noise

S = TaskStatus


@dataclass
class RunSummary:
    run_id: str
    task_ids: list[str]
    statuses: dict[str, str] = field(default_factory=dict)

    @property
    def any_failed(self) -> bool:
        return any(s == S.FAILED.value for s in self.statuses.values())

    @property
    def all_cancelled(self) -> bool:
        return bool(self.statuses) and all(s == S.CANCELLED.value for s in self.statuses.values())


def new_run_id() -> str:
    return "r" + secrets.token_hex(3)


class Orchestrator:
    def __init__(
        self,
        paths: ProjectPaths,
        settings: Settings,
        store: Store,
        *,
        registry: AgentRegistry | None = None,
        policy_profile: PolicyProfile | None = None,
        on_event: EventCallback | None = None,
        sleep: Callable[[float], Any] = asyncio.sleep,
    ) -> None:
        self.paths = paths
        self.settings = settings
        self.store = store
        self.registry = registry or AgentRegistry(settings)
        self.policy: Policy = build_policy(
            policy_profile or settings.security.policy, settings.security.extra_allowed_commands
        )
        self.router = Router(settings, self.registry, self.policy)
        self.events = EventRecorder(store, paths.logs_dir, on_event)
        self.workspaces = WorkspaceManager(
            paths.root, paths.worktrees_dir(settings), settings.workspace.branch_prefix
        )
        self.validator = ValidationEngine(
            settings.validation, self.policy, cache_dir=paths.state_dir / "cache"
        )
        self._sleep = sleep
        paths.ensure()

    # ------------------------------------------------------------ helpers
    def _transition(
        self, task_id: str, target: TaskStatus, message: str, **fields: Any
    ) -> TaskRecord:
        task = self.store.transition(task_id, target, message, **fields)
        self.events.transitioned(task_id, target.value, message)
        return task

    def recover(self) -> list[str]:
        return recover_stale_tasks(
            self.store,
            self.registry,
            self.settings.orchestration.stale_after_seconds,
            self.events,
        )

    # ----------------------------------------------------------- planning
    async def plan(self, objective: str, mode: str | None = None) -> Plan:
        mode = mode or self.settings.orchestration.planner_mode
        if mode == "single":
            return single_plan(objective)
        if mode == "standard":
            return standard_plan(objective)
        if mode == "provider":
            name = self.settings.routing.planner
            adapter = self.registry.get(name)
            capabilities = await adapter.get_capabilities()
            if Capability.PLAN not in capabilities.capabilities:
                raise PolicyViolationError(f"Planner provider '{name}' does not declare 'plan'")
            plan, warnings = await provider_plan(
                objective,
                adapter,
                self.paths.root,
                self.paths.artifacts_dir / "planning",
                self.settings.orchestration.task_timeout_seconds,
            )
            plan.warnings = sorted(set(plan.warnings) | set(warnings))
            return plan
        raise InvalidStateError(f"Unknown planner mode: {mode}")

    async def submit(
        self,
        objective: str,
        *,
        provider: str | None = None,
        planner_mode: str | None = None,
        plan: Plan | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Plan an objective and persist the run and its tasks (all PENDING)."""
        if not objective.strip():
            raise InvalidStateError("Objective must not be empty")
        plan = plan or await self.plan(objective, planner_mode)
        git = Git(self.paths.root)
        base_branch = base_commit = None
        if git.is_repository() and git.has_commits():
            base_branch = git.current_branch()
            base_commit = git.head()
            if git.status_porcelain(include_untracked=False):
                plan.warnings.append(
                    "The primary working tree has uncommitted changes; they are NOT included "
                    "in task workspaces (tasks start from the last commit)."
                )
        run_id = new_run_id()
        self.store.add_run(
            RunRecord(
                id=run_id,
                project_id=self.settings.project.name,
                objective=objective,
                planner=planner_mode or self.settings.orchestration.planner_mode,
                plan=plan.model_dump(mode="json"),
                warnings=plan.warnings,
                policy=self.policy.profile.value,
                base_branch=base_branch,
                base_commit=base_commit,
            )
        )
        for spec in plan.tasks:
            task_id = f"{run_id}-{spec.id}"
            extra: dict[str, Any] = {"preferred_provider": provider, **(metadata or {})}
            self.store.add_task(
                TaskRecord(
                    id=task_id,
                    run_id=run_id,
                    project_id=self.settings.project.name,
                    key=spec.id,
                    title=spec.title,
                    description=spec.description,
                    role=spec.role.value,
                    status=S.PENDING.value,
                    priority=spec.priority,
                    dependencies=[f"{run_id}-{dep}" for dep in spec.dependencies],
                    acceptance_criteria=spec.acceptance_criteria,
                    expected_files=spec.expected_files,
                    risk_level=spec.risk_level.value,
                    timeout_seconds=spec.timeout_seconds,
                    extra=extra
                    | {"required_capabilities": [c.value for c in spec.required_capabilities]},
                )
            )
        for warning in plan.warnings:
            self.events.emit("plan.warning", warning, run_id=run_id)
        self.events.emit(
            "run.created", f"Run {run_id} planned with {len(plan.tasks)} task(s)", run_id=run_id
        )
        return run_id

    # ---------------------------------------------------------- scheduling
    @staticmethod
    def _dependency_satisfied(task: TaskRecord) -> bool:
        if task.status == S.SUCCEEDED.value:
            return True
        # Validated changes awaiting merge approval can feed downstream tasks; the
        # downstream workspace is based on the upstream branch.
        return task.status == S.WAITING_FOR_APPROVAL.value and task.waiting_reason in (
            WaitingReason.MERGE_APPROVAL.value,
            WaitingReason.HUMAN_REVIEW.value,
        )

    def _promote_ready(self, run_id: str) -> None:
        # Repeat until stable so failures propagate down whole dependency chains.
        changed = True
        while changed:
            changed = False
            tasks = {t.id: t for t in self.store.list_tasks(run_id=run_id)}
            for task in tasks.values():
                if task.status != S.PENDING.value:
                    continue
                deps = [tasks[d] for d in task.dependencies if d in tasks]
                blocked = [d for d in deps if d.status in (S.FAILED.value, S.CANCELLED.value)]
                if blocked:
                    self._transition(
                        task.id,
                        S.FAILED,
                        f"Dependency {blocked[0].id} is {blocked[0].status}",
                        error_message=f"Dependency {blocked[0].id} did not succeed",
                    )
                    changed = True
                elif all(self._dependency_satisfied(d) for d in deps):
                    self._transition(task.id, S.READY, "All dependencies satisfied")
                    changed = True

    async def execute_run(self, run_id: str) -> RunSummary:
        """Run every eligible task of a run, respecting dependencies and concurrency."""
        limit = self.settings.orchestration.max_parallel_tasks
        running: dict[str, asyncio.Task[None]] = {}
        while True:
            self._promote_ready(run_id)
            tasks = self.store.list_tasks(run_id=run_id)
            ready = sorted(
                (t for t in tasks if t.status == S.READY.value and t.id not in running),
                key=lambda t: (-t.priority, t.id),
            )
            for task in ready[: max(0, limit - len(running))]:
                self._transition(task.id, S.QUEUED, "Queued for execution")
                running[task.id] = asyncio.create_task(self._guarded_run_task(task.id))
            if not running:
                break
            done, _ = await asyncio.wait(running.values(), return_when=asyncio.FIRST_COMPLETED)
            for finished in done:
                for key, value in list(running.items()):
                    if value is finished:
                        running.pop(key)
        summary = RunSummary(run_id, [t.id for t in self.store.list_tasks(run_id=run_id)])
        summary.statuses = {t.id: t.status for t in self.store.list_tasks(run_id=run_id)}
        write_run_report(self.store, run_id, self.paths.reports_dir)
        return summary

    async def _guarded_run_task(self, task_id: str) -> None:
        try:
            await self.run_task(task_id)
        except AgentBridgeError as exc:
            self._fail_safely(task_id, exc.message)
        except Exception as exc:
            self._fail_safely(task_id, f"Internal error: {type(exc).__name__}: {exc}")
        finally:
            write_task_report(self.store, task_id, self.paths.reports_dir)

    def _fail_safely(self, task_id: str, message: str) -> None:
        task = self.store.get_task(task_id)
        status = S(task.status)
        self.events.emit("task.error", message, task_id=task_id, run_id=task.run_id)
        if status in ACTIVE_STATUSES or status in (S.READY, S.PENDING):
            with contextlib.suppress(AgentBridgeError):
                self._transition(task_id, S.FAILED, message, error_message=message)

    # -------------------------------------------------------------- tasks
    def _spec(self, task: TaskRecord) -> TaskSpec:
        return TaskSpec(
            id=task.key,
            title=task.title,
            description=task.description,
            role=TaskRole(task.role),
            acceptance_criteria=task.acceptance_criteria,
            expected_files=task.expected_files,
            required_capabilities=[
                Capability(c) for c in task.extra.get("required_capabilities", [])
            ],
        )

    def _prepare_workspace(
        self, task: TaskRecord, adapter_caps: frozenset[Capability]
    ) -> Workspace | None:
        if Capability.REMOTE_WORKSPACE in adapter_caps and Capability.LOCAL_WORKSPACE not in (
            adapter_caps
        ):
            return None  # remote providers never see local worktrees
        run = self.store.get_run(task.run_id)
        deps = [self.store.get_task(d) for d in task.dependencies]
        dep_branches = [d.git_branch for d in deps if d.git_branch and d.head_commit]
        if self.settings.workspace.use_git_worktree:
            base_ref = dep_branches[0] if dep_branches else run.base_commit
            return self.workspaces.create_worktree(
                task.id, task.title, base_ref=base_ref, merge_branches=dep_branches[1:]
            )
        return self.workspaces.create_directory_workspace(task.id)

    def _upstream_summaries(self, task: TaskRecord) -> list[str]:
        summaries = []
        for dep_id in task.dependencies:
            dep = self.store.get_task(dep_id)
            if dep.result_summary:
                summaries.append(f"{dep.key} ({dep.role}): {dep.result_summary[:1500]}")
        return summaries

    async def run_task(self, task_id: str) -> None:
        task = self.store.get_task(task_id)
        spec = self._spec(task)
        preferred = task.extra.get("preferred_provider")
        # An explicitly requested provider is used for work tasks; reviews keep
        # their own routing so they stay independent where configured.
        if spec.role is TaskRole.REVIEWER and self.settings.routing.reviewer:
            preferred = None
        decision = await self.router.route(spec.role, spec.effective_capabilities(), preferred)
        adapter = self.registry.get(decision.provider)
        capabilities = (await adapter.get_capabilities()).capabilities
        self.events.emit("task.routed", decision.explain(), task_id=task_id, run_id=task.run_id)
        workspace = self._prepare_workspace(task, capabilities)
        run = self.store.get_run(task.run_id)
        fields: dict[str, Any] = {
            "assigned_provider": decision.provider,
            "routing_reason": decision.explain(),
        }
        if workspace is not None:
            fields |= {
                "workspace_path": str(workspace.path),
                "workspace_kind": workspace.kind,
                "git_branch": workspace.branch,
                "base_branch": run.base_branch or workspace.base_branch,
                "base_commit": Git(workspace.path).head(),
            }
        else:
            fields |= {
                "workspace_kind": "remote",
                "base_branch": run.base_branch,
                "base_commit": run.base_commit,
            }
        self.store.update_task(task_id, **fields)
        self._transition(task_id, S.RUNNING, f"Dispatched to {decision.provider}")
        await self._execute_attempts(task_id, adapter, workspace)

    async def _heartbeat(self, task_id: str, adapter: AgentAdapter, execution_id: str) -> None:
        interval = self.settings.orchestration.heartbeat_seconds
        while True:
            task = self.store.update_task(task_id, heartbeat_at=utcnow())
            if task.cancel_requested:
                await adapter.cancel(execution_id)
            await asyncio.sleep(interval)

    async def _execute_attempts(
        self, task_id: str, adapter: AgentAdapter, workspace: Workspace | None
    ) -> None:
        orchestration = self.settings.orchestration
        while True:
            task = self.store.get_task(task_id)
            if task.cancel_requested:
                self._transition(task_id, S.CANCELLED, "Cancelled before execution")
                return
            attempt = len(self.store.list_executions(task_id)) + 1
            execution_id = f"{task_id}-a{attempt}"
            request = self._build_request(task, attempt, execution_id, workspace)
            self.store.add_execution(
                ExecutionRecord(
                    id=execution_id,
                    task_id=task_id,
                    provider=adapter.name,
                    attempt=attempt,
                    status=ExecutionState.RUNNING.value,
                )
            )
            self.store.update_task(task_id, execution_id=execution_id)
            self.events.emit(
                "execution.started",
                f"Attempt {attempt} on {adapter.name}",
                task_id=task_id,
                run_id=task.run_id,
            )
            snapshot = self._primary_snapshot()
            heartbeat = asyncio.create_task(self._heartbeat(task_id, adapter, execution_id))
            try:
                result = await adapter.execute(request)
            finally:
                heartbeat.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat
            self._record_execution(result)
            self.events.emit(
                "execution.finished",
                f"Attempt {attempt}: {result.state.value}"
                + (f" ({result.error})" if result.error else ""),
                task_id=task_id,
                run_id=task.run_id,
                data={"duration_seconds": result.duration_seconds},
            )
            if result.state is ExecutionState.COMPLETED:
                self.store.update_task(task_id, result_summary=result.summary)
                await self._after_execution(task_id, workspace, snapshot)
                return
            if result.state is ExecutionState.HANDOFF_PREPARED:
                self._transition(
                    task_id,
                    S.WAITING_FOR_APPROVAL,
                    result.summary,
                    waiting_reason=WaitingReason.REMOTE_HANDOFF.value,
                    result_summary=result.summary,
                    extra=task.extra
                    | {"handoff_artifacts": result.artifacts, "human_interventions": 1},
                )
                return
            if (
                result.state is ExecutionState.CANCELLED
                or self.store.get_task(task_id).cancel_requested
            ):
                self._transition(task_id, S.CANCELLED, "Cancelled by user")
                return
            if result.state is ExecutionState.INTERRUPTED:
                self._transition(
                    task_id,
                    S.INTERRUPTED,
                    result.error or "Execution interrupted",
                    error_message=result.error,
                )
                return
            if result.retryable and task.retry_count < orchestration.retry_limit:
                delay = orchestration.retry_backoff_seconds * (2**task.retry_count)
                self._transition(
                    task_id,
                    S.QUEUED,
                    f"Retry {task.retry_count + 1}/{orchestration.retry_limit} in {delay:.1f}s "
                    f"after {result.state.value}",
                    retry_count=task.retry_count + 1,
                    error_message=result.error,
                )
                await self._sleep(delay)
                self._transition(task_id, S.RUNNING, "Retrying")
                continue
            self._transition(
                task_id,
                S.FAILED,
                result.error or f"Execution {result.state.value}",
                error_message=result.error or result.state.value,
                result_summary=result.summary or None,
            )
            return

    def _build_request(
        self, task: TaskRecord, attempt: int, execution_id: str, workspace: Workspace | None
    ) -> ExecutionRequest:
        role = TaskRole(task.role)
        may_edit = role in EDITING_ROLES and self.policy.agents_may_edit
        timeout = task.timeout_seconds or self.settings.orchestration.task_timeout_seconds
        provider_settings = self.settings.providers.get(task.assigned_provider or "")
        if provider_settings and provider_settings.timeout_seconds:
            timeout = min(timeout, provider_settings.timeout_seconds)
        return ExecutionRequest(
            task_id=task.id,
            execution_id=execution_id,
            attempt=attempt,
            title=task.title,
            description=task.description,
            role=task.role,
            prompt=task_prompt(
                title=task.title,
                description=task.description,
                role=task.role,
                acceptance_criteria=task.acceptance_criteria,
                expected_files=task.expected_files,
                may_edit=may_edit,
                upstream_summaries=self._upstream_summaries(task),
            ),
            acceptance_criteria=task.acceptance_criteria,
            expected_files=task.expected_files,
            workdir=workspace.path if workspace else None,
            output_dir=self.paths.artifacts_dir / task.id,
            timeout_seconds=timeout,
            agents_may_edit=may_edit,
            permission_mode=self.policy.claude_permission_mode if may_edit else "plan",
            repository_info={
                "root": str(self.paths.root),
                "base_branch": task.base_branch,
                "base_commit": task.base_commit,
            },
            metadata={k: v for k, v in task.extra.items() if k.startswith("mock_")},
        )

    def _record_execution(self, result: ExecutionResult) -> None:
        usage = result.usage
        self.store.update_execution(
            result.execution_id,
            status=result.state.value,
            finished_at=utcnow(),
            duration_seconds=result.duration_seconds,
            exit_code=result.exit_code,
            output_path=result.output_path,
            summary=result.summary[-8000:] if result.summary else None,
            error=result.error,
            model=usage.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=usage.cost_usd,
            cost_source=(f"{usage.cost_kind}:{usage.cost_source}" if usage.cost_source else None),
            data=result.metadata | {"artifacts": result.artifacts},
        )

    def _primary_snapshot(self) -> list[str] | None:
        git = Git(self.paths.root)
        if not git.is_repository():
            return None
        return git.status_porcelain()

    # --------------------------------------------------------- validation
    async def _after_execution(
        self, task_id: str, workspace: Workspace | None, snapshot: list[str] | None
    ) -> None:
        task = self.store.get_task(task_id)
        role = TaskRole(task.role)
        extra_steps: list[StepResult] = []
        if snapshot is not None:
            after = self._primary_snapshot()
            if after != snapshot:
                extra_steps.append(
                    StepResult(
                        name="isolation",
                        outcome=Outcome.FAIL,
                        summary="The primary working tree changed during agent execution",
                        details={"before": snapshot, "after": after},
                    )
                )
            else:
                extra_steps.append(
                    StepResult(
                        name="isolation",
                        outcome=Outcome.PASS,
                        summary="Primary working tree unchanged",
                    )
                )
        if workspace is None:
            self._transition(task_id, S.FAILED, "No local workspace to validate")
            return
        head = self.workspaces.commit_changes(
            workspace.path,
            f"AgentBridge {task.id}: {task.title}\n\nProvider: "
            f"{task.assigned_provider}\nExecution: {task.execution_id}",
        )
        if head:
            self.store.update_task(task_id, head_commit=head)
        if role is TaskRole.REVIEWER:
            extra_steps.append(self._verdict_step(task.result_summary or ""))
        self._transition(task_id, S.VALIDATING, "Running independent validation")
        await self._validate(task_id, extra_steps)

    @staticmethod
    def _verdict_step(text: str) -> StepResult:
        upper = text.upper()
        if "VERDICT: CHANGES_REQUESTED" in upper:
            return StepResult(
                name="agent_review",
                outcome=Outcome.NEEDS_HUMAN_REVIEW,
                summary="Reviewer requested changes",
            )
        if "VERDICT: PASS" in upper:
            return StepResult(
                name="agent_review", outcome=Outcome.PASS, summary="Reviewer verdict: PASS"
            )
        return StepResult(
            name="agent_review",
            outcome=Outcome.NEEDS_HUMAN_REVIEW,
            summary="Reviewer gave no explicit verdict",
        )

    async def _agent_review_step(self, task: TaskRecord) -> StepResult | None:
        """Optional independent agent review of an editing task's diff."""
        reviewer = self.settings.routing.reviewer
        if not reviewer or TaskRole(task.role) not in EDITING_ROLES or not task.head_commit:
            return None
        adapter = self.registry.get(reviewer)
        caps = await adapter.get_capabilities()
        if Capability.REVIEW not in caps.capabilities or task.workspace_path is None:
            return StepResult(
                name="agent_review",
                outcome=Outcome.WARNING,
                summary=f"Reviewer '{reviewer}' cannot review local changes",
            )
        execution_id = f"{task.id}-review{len(self.store.list_validations(task.id)) + 1}"
        request = ExecutionRequest(
            task_id=task.id,
            execution_id=execution_id,
            title=f"Review: {task.title}",
            description=f"Review the diff between {task.base_commit} and HEAD.",
            role=TaskRole.REVIEWER.value,
            prompt=task_prompt(
                title=f"Review changes for: {task.title}",
                description=(
                    f"Run 'git diff {task.base_commit} HEAD' to see the changes. Check them "
                    "against the acceptance criteria."
                ),
                role=TaskRole.REVIEWER.value,
                acceptance_criteria=task.acceptance_criteria,
                expected_files=task.expected_files,
                may_edit=False,
            ),
            workdir=Path(task.workspace_path),
            output_dir=self.paths.artifacts_dir / task.id,
            timeout_seconds=self.settings.orchestration.task_timeout_seconds,
            agents_may_edit=False,
            permission_mode="plan",
        )
        result = await adapter.execute(request)
        if result.state is not ExecutionState.COMPLETED:
            return StepResult(
                name="agent_review",
                outcome=Outcome.NEEDS_HUMAN_REVIEW,
                summary=f"Reviewer did not complete: {result.state.value}",
            )
        step = self._verdict_step(result.summary)
        same = reviewer == task.assigned_provider
        step.details = {
            "reviewer": reviewer,
            "same_provider_as_worker": same,
            "review": result.summary[-4000:],
        }
        if same:
            step.summary += " (same provider as worker; not fully independent)"
        return step

    async def _validate(self, task_id: str, extra_steps: list[StepResult]) -> ValidationReport:
        task = self.store.get_task(task_id)
        role = TaskRole(task.role)
        if task.workspace_path is None or task.base_commit is None:
            raise InvalidStateError(f"Task {task_id} has no workspace to validate")
        workdir = Path(task.workspace_path)
        expect_changes = role in EDITING_ROLES
        report = await self.validator.validate(
            workdir,
            task.base_commit,
            expected_files=task.expected_files,
            expect_changes=expect_changes,
            extra_steps=extra_steps,
        )
        if not expect_changes and report.changed_files:
            report.steps.append(
                StepResult(
                    name="read_only",
                    outcome=Outcome.NEEDS_HUMAN_REVIEW,
                    summary=f"A read-only {role.value} task modified {len(report.changed_files)} "
                    "file(s)",
                )
            )
        review_step = await self._agent_review_step(self.store.get_task(task_id))
        if review_step is not None:
            report.steps.append(review_step)
        report.outcome = aggregate(report.steps)
        self.store.add_validation(task_id, report.outcome.value, report.model_dump(mode="json"))
        self.store.update_task(
            task_id,
            changed_files=report.changed_files,
            validation_outcome=report.outcome.value,
            head_commit=report.head_commit if report.changed_files else task.head_commit,
        )
        self.events.emit(
            "validation.finished",
            f"Validation {report.outcome.value}",
            task_id=task_id,
            run_id=task.run_id,
        )
        if report.outcome is Outcome.FAIL:
            failed = [s.name for s in report.steps if s.outcome is Outcome.FAIL]
            self._transition(
                task_id,
                S.FAILED,
                f"Validation failed: {', '.join(failed)}",
                error_message=f"Validation failed: {', '.join(failed)}",
            )
        elif not report.changed_files and report.outcome is not Outcome.NEEDS_HUMAN_REVIEW:
            self._transition(
                task_id, S.SUCCEEDED, "Validated; no changes to integrate", waiting_reason=None
            )
        else:
            reason = (
                WaitingReason.HUMAN_REVIEW
                if report.outcome is Outcome.NEEDS_HUMAN_REVIEW
                else WaitingReason.MERGE_APPROVAL
            )
            self._transition(
                task_id,
                S.WAITING_FOR_APPROVAL,
                f"Validation {report.outcome.value}; awaiting human approval",
                waiting_reason=reason.value,
            )
        return report

    # --------------------------------------------------------- approvals
    def approve(self, task_id: str) -> str:
        task = self.store.get_task(task_id)
        if task.status != S.WAITING_FOR_APPROVAL.value:
            raise InvalidStateError(f"Task {task_id} is {task.status}, not awaiting approval")
        if task.waiting_reason == WaitingReason.REMOTE_HANDOFF.value:
            raise InvalidStateError(
                "This task is waiting for a remote result, not for merge approval",
                hint=f"Import the remote result first: agentbridge remote import {task_id} "
                "--branch <branch>",
            )
        self.events.emit(
            "approval.granted", "Merge approved by user", task_id=task_id, run_id=task.run_id
        )
        if not task.changed_files or not task.git_branch or task.workspace_kind != "git_worktree":
            self._transition(
                task_id, S.SUCCEEDED, "Approved; nothing to merge", waiting_reason=None
            )
            return "Approved; there were no changes to merge."
        target = task.base_branch or self.settings.project.default_branch
        workspace_git = Git(Path(task.workspace_path or "."))
        if task.workspace_path and without_tool_noise(workspace_git.status_porcelain()):
            raise InvalidStateError(
                f"Task worktree {task.workspace_path} has uncommitted changes made after "
                "validation; refusing to merge unvalidated work",
                hint=f"Re-validate with: agentbridge tasks resume {task_id} --revalidate",
            )
        primary = Git(self.paths.root)
        if primary.current_branch() != target:
            raise InvalidStateError(
                f"Primary checkout is on {primary.current_branch()!r}, expected {target!r}",
                hint=f"git switch {target}",
            )
        if primary.status_porcelain(include_untracked=False):
            raise InvalidStateError(
                "The primary working tree has uncommitted changes; refusing to merge",
                hint="Commit or stash your own changes first.",
            )
        self._transition(task_id, S.INTEGRATING, f"Merging {task.git_branch} into {target}")
        try:
            result = merge_branch(
                self.paths.root,
                task.git_branch,
                target,
                f"Merge AgentBridge task {task.id}: {task.title}",
            )
        except (GitError, InvalidStateError) as exc:
            self._transition(task_id, S.WAITING_FOR_APPROVAL, f"Merge blocked: {exc.message}")
            raise
        if not result.merged:
            self._transition(task_id, S.WAITING_FOR_APPROVAL, result.message)
            raise GitError(result.message, hint="Resolve the conflict manually, then retry.")
        self._transition(
            task_id,
            S.SUCCEEDED,
            result.message,
            waiting_reason=None,
            extra=task.extra | {"merge_commit": result.commit},
        )
        write_task_report(self.store, task_id, self.paths.reports_dir)
        return result.message

    def reject(self, task_id: str, reason: str = "Rejected by user") -> None:
        task = self.store.get_task(task_id)
        if task.status != S.WAITING_FOR_APPROVAL.value:
            raise InvalidStateError(f"Task {task_id} is {task.status}, not awaiting approval")
        self._transition(task_id, S.CANCELLED, reason, waiting_reason=None)
        write_task_report(self.store, task_id, self.paths.reports_dir)

    def request_cancel(self, task_id: str) -> str:
        task = self.store.get_task(task_id)
        status = S(task.status)
        if status in (S.SUCCEEDED, S.CANCELLED):
            raise InvalidStateError(f"Task {task_id} is already {status.value}")
        if status is S.INTEGRATING:
            raise InvalidStateError("Task is merging; cancellation is not safe right now")
        self.store.update_task(task_id, cancel_requested=True)
        stale = recover_stale_tasks(
            self.store,
            self.registry,
            self.settings.orchestration.stale_after_seconds,
            self.events,
            only=[task_id],
            mark=False,
        )
        if status in ACTIVE_STATUSES and task_id not in stale:
            return "Cancellation requested; the running process will stop the agent."
        self._transition(task_id, S.CANCELLED, "Cancelled by user")
        return "Task cancelled."

    # ----------------------------------------------------------- recovery
    async def resume(self, task_id: str, *, rerun: bool = False, revalidate: bool = False) -> str:
        self.recover()
        task = self.store.get_task(task_id)
        status = S(task.status)
        workspace_has_work = False
        if task.workspace_path and Path(task.workspace_path).exists() and task.base_commit:
            git = Git(Path(task.workspace_path))
            workspace_has_work = (
                bool(without_tool_noise(git.status_porcelain())) or git.head() != task.base_commit
            )

        if status is S.WAITING_FOR_APPROVAL and revalidate:
            if task.waiting_reason == WaitingReason.REMOTE_HANDOFF.value:
                raise InvalidStateError("Use 'agentbridge remote import' for remote tasks")
            if task.workspace_path:
                head = self.workspaces.commit_changes(
                    Path(task.workspace_path), f"AgentBridge {task.id}: post-review edits"
                )
                if head:
                    self.store.update_task(task_id, head_commit=head)
            self._transition(task_id, S.VALIDATING, "Re-validation requested")
            await self._validate(task_id, [])
        elif status is S.INTERRUPTED:
            if workspace_has_work and not rerun:
                # Never re-run an agent whose work may already exist: validate it.
                head = self.workspaces.commit_changes(
                    Path(task.workspace_path or "."),
                    f"AgentBridge {task.id}: recovered work after interruption",
                )
                if head:
                    self.store.update_task(task_id, head_commit=head)
                self._transition(
                    task_id, S.VALIDATING, "Recovered existing workspace changes; validating"
                )
                await self._validate(task_id, [])
            elif rerun:
                self._transition(task_id, S.QUEUED, "Re-run requested by user after interruption")
                await self._requeue_run(task_id)
            else:
                raise InvalidStateError(
                    "The interrupted execution may or may not have completed, and its "
                    "workspace shows no changes",
                    hint=f"Re-run explicitly with: agentbridge tasks resume {task_id} --rerun",
                )
        elif status is S.FAILED:
            if not rerun:
                raise InvalidStateError(
                    f"Task {task_id} failed: {task.error_message}",
                    hint=f"Re-run explicitly with: agentbridge tasks resume {task_id} --rerun",
                )
            self.store.update_task(task_id, cancel_requested=False)
            self._transition(task_id, S.QUEUED, "Re-run requested by user after failure")
            await self._requeue_run(task_id)
        elif status in (S.PENDING, S.READY):
            await self.execute_run(task.run_id)
        else:
            raise InvalidStateError(f"Task {task_id} is {status.value}; nothing to resume")
        write_task_report(self.store, task_id, self.paths.reports_dir)
        # Downstream tasks may now be eligible.
        await self.execute_run(task.run_id)
        return self.store.get_task(task_id).status

    async def _requeue_run(self, task_id: str) -> None:
        task = self.store.get_task(task_id)
        if task.workspace_path is None and task.workspace_kind != "remote":
            await self._guarded_run_task(task_id)
            return
        # Workspace already exists: re-dispatch into it.
        try:
            adapter = self.registry.get(task.assigned_provider or "")
            workspace = None
            if task.workspace_path:
                workspace = Workspace(
                    Path(task.workspace_path),
                    task.workspace_kind or "git_worktree",
                    task.git_branch,
                    task.base_branch,
                    task.base_commit,
                )
            self._transition(task_id, S.RUNNING, f"Re-dispatched to {adapter.name}")
            await self._execute_attempts(task_id, adapter, workspace)
        except AgentBridgeError as exc:
            self._fail_safely(task_id, exc.message)
        finally:
            write_task_report(self.store, task_id, self.paths.reports_dir)

    # -------------------------------------------------------- remote import
    async def import_remote(
        self, task_id: str, branch: str, remote: str | None = None
    ) -> ValidationReport:
        task = self.store.get_task(task_id)
        if task.status != S.WAITING_FOR_APPROVAL.value or (
            task.waiting_reason != WaitingReason.REMOTE_HANDOFF.value
        ):
            raise InvalidStateError(f"Task {task_id} is not waiting for a remote result")
        git = Git(self.paths.root)
        if git.run("check-ref-format", "--branch", branch, check=False).returncode != 0:
            raise PolicyViolationError(f"Invalid branch name: {branch!r}")
        if remote:
            if remote not in git.out("remote").split():
                raise GitError(f"Git remote {remote!r} is not configured")
            git.run("fetch", "--no-tags", remote, f"refs/heads/{branch}")
            ref = git.out("rev-parse", "FETCH_HEAD")
        else:
            if not git.branch_exists(branch):
                raise GitError(f"Local branch {branch!r} does not exist")
            ref = git.out("rev-parse", branch)
        steps: list[StepResult] = []
        base = task.base_commit
        if base and git.run("merge-base", "--is-ancestor", base, ref, check=False).returncode:
            steps.append(
                StepResult(
                    name="base_check",
                    outcome=Outcome.NEEDS_HUMAN_REVIEW,
                    summary=f"Imported branch does not descend from base commit {base[:12]}",
                )
            )
        else:
            steps.append(
                StepResult(
                    name="base_check",
                    outcome=Outcome.PASS,
                    summary="Imported branch descends from the base commit",
                )
            )
        workspace = self.workspaces.create_worktree(task_id, task.title, base_ref=ref)
        self.store.update_task(
            task_id,
            workspace_path=str(workspace.path),
            workspace_kind=workspace.kind,
            git_branch=workspace.branch,
            head_commit=ref,
            base_commit=base or workspace.base_commit,
            extra=task.extra
            | {
                "imported_from": f"{remote + '/' if remote else ''}{branch}",
                "human_interventions": int(task.extra.get("human_interventions", 1)),
            },
        )
        self.events.emit(
            "remote.imported",
            f"Imported {branch} at {ref[:12]}",
            task_id=task_id,
            run_id=task.run_id,
        )
        self._transition(task_id, S.VALIDATING, "Validating imported remote result")
        report = await self._validate(task_id, steps)
        write_task_report(self.store, task_id, self.paths.reports_dir)
        return report


def current_pid() -> int:
    return os.getpid()
