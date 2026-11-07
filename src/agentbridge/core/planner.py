"""Objective -> validated task plan.

Modes:
- ``single``: one developer task (deterministic).
- ``standard``: analyse -> implement -> review (deterministic template).
- ``provider``: ask the planner provider for a JSON plan and validate it with
  Pydantic. Invalid output falls back to ``single`` with a recorded warning.
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from agentbridge.agents.base import AgentAdapter, ExecutionRequest, ExecutionState
from agentbridge.agents.prompts import planning_prompt
from agentbridge.errors import PlanValidationError
from agentbridge.tasks.models import Plan, TaskRole, TaskSpec
from agentbridge.workspace.git import Git

_JSON_BLOCK = re.compile(r"\{[\s\S]*\}")


def _title(objective: str) -> str:
    first_line = objective.strip().splitlines()[0] if objective.strip() else "Task"
    return first_line[:200]


def single_plan(objective: str) -> Plan:
    return Plan(
        objective=objective,
        tasks=[
            TaskSpec(
                id="task-001",
                title=_title(objective),
                description=objective,
                role=TaskRole.DEVELOPER,
                acceptance_criteria=["The objective is implemented", "Validation checks pass"],
            )
        ],
    )


def standard_plan(objective: str) -> Plan:
    return Plan(
        objective=objective,
        tasks=[
            TaskSpec(
                id="task-001",
                title="Analyze repository for: " + _title(objective)[:150],
                description=f"Analyse the repository and summarise what is needed to: {objective}",
                role=TaskRole.ANALYST,
                acceptance_criteria=["Analysis summary exists"],
            ),
            TaskSpec(
                id="task-002",
                title=_title(objective),
                description=objective,
                role=TaskRole.DEVELOPER,
                dependencies=["task-001"],
                acceptance_criteria=["The objective is implemented", "Validation checks pass"],
            ),
            TaskSpec(
                id="task-003",
                title="Review and validate implementation",
                description=f"Independently review the implementation of: {objective}",
                role=TaskRole.REVIEWER,
                dependencies=["task-002"],
                acceptance_criteria=["Review verdict recorded"],
            ),
        ],
    )


def parse_plan(payload: Any, objective: str) -> Plan:
    """Validate untrusted planner output."""
    if isinstance(payload, str):
        match = _JSON_BLOCK.search(payload)
        if not match:
            raise PlanValidationError("Planner output contains no JSON object")
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise PlanValidationError(f"Planner output is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlanValidationError("Planner output must be a JSON object")
    payload = {**payload, "objective": payload.get("objective") or objective}
    # Planners must not smuggle extra fields; strip unknown keys per task explicitly.
    allowed = set(TaskSpec.model_fields)
    tasks = payload.get("tasks")
    if isinstance(tasks, list):
        payload["tasks"] = [
            {k: v for k, v in t.items() if k in allowed} if isinstance(t, dict) else t
            for t in tasks
        ]
    payload = {k: v for k, v in payload.items() if k in ("objective", "tasks")}
    try:
        return Plan.model_validate(payload)
    except ValidationError as exc:
        raise PlanValidationError(f"Planner output failed validation: {exc}") from exc


def repository_overview(root: Path, limit: int = 200) -> str:
    git = Git(root)
    if git.is_repository() and git.has_commits():
        files = git.out("ls-files").splitlines()
    else:
        files = sorted(
            str(p.relative_to(root)).replace("\\", "/")
            for p in root.rglob("*")
            if p.is_file() and ".git" not in p.parts and ".agentbridge" not in p.parts
        )
    shown = files[:limit]
    more = f"\n... and {len(files) - limit} more files" if len(files) > limit else ""
    return "\n".join(shown) + more


async def provider_plan(
    objective: str,
    adapter: AgentAdapter,
    repo_root: Path,
    output_dir: Path,
    timeout: int,
) -> tuple[Plan, list[str]]:
    """Ask a provider for a plan. Returns (plan, warnings)."""
    request = ExecutionRequest(
        task_id="planning",
        execution_id=f"plan-{uuid.uuid4().hex[:8]}",
        title=f"Plan: {_title(objective)}",
        description=objective,
        role=TaskRole.PLANNER.value,
        prompt=planning_prompt(objective, repository_overview(repo_root)),
        workdir=repo_root,
        output_dir=output_dir,
        timeout_seconds=timeout,
        agents_may_edit=False,
        metadata={"objective": objective},
    )
    result = await adapter.execute(request)
    if result.state is not ExecutionState.COMPLETED:
        warning = f"Planner provider failed ({result.state.value}): {result.error}; using single"
        return single_plan(objective), [warning]
    try:
        plan = parse_plan(result.structured_output or result.summary, objective)
    except PlanValidationError as exc:
        return single_plan(objective), [f"{exc.message}; using single-task plan"]
    return plan, []
