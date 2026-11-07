"""Prompt construction for coding agents."""

from __future__ import annotations

import json
from collections.abc import Sequence

from agentbridge.tasks.models import TaskRole

PLAN_SCHEMA_HINT = {
    "objective": "string",
    "tasks": [
        {
            "id": "task-001",
            "title": "string",
            "description": "string",
            "role": "analyst | developer | tester | documenter | reviewer",
            "dependencies": ["task ids"],
            "acceptance_criteria": ["string"],
            "expected_files": ["relative/paths"],
            "risk_level": "low | medium | high",
        }
    ],
}


def task_prompt(
    *,
    title: str,
    description: str,
    role: str,
    acceptance_criteria: Sequence[str],
    expected_files: Sequence[str],
    may_edit: bool,
    upstream_summaries: Sequence[str] = (),
) -> str:
    lines = [
        "You are working on a task delegated by AgentBridge.",
        f"Role: {role}",
        f"Task: {title}",
    ]
    if description and description != title:
        lines += ["", "Details:", description]
    if acceptance_criteria:
        lines += ["", "Acceptance criteria:"] + [f"- {item}" for item in acceptance_criteria]
    if expected_files:
        lines += ["", "Expected scope (files):"] + [f"- {item}" for item in expected_files]
    if upstream_summaries:
        lines += ["", "Results of prerequisite tasks:"] + [f"- {s}" for s in upstream_summaries]
    lines += [""]
    if may_edit:
        lines += [
            "Work only inside the current working directory. Make the required file changes",
            "directly. Do not commit, push, or modify git configuration; AgentBridge commits",
            "and validates your changes independently.",
        ]
    else:
        lines += ["Do not modify any files. Analyse and report only."]
    if role == TaskRole.REVIEWER.value:
        lines += [
            "Review the changes on the current branch against the base commit. Report",
            "concrete defects first, then risks. Begin your answer with 'VERDICT: PASS'",
            "or 'VERDICT: CHANGES_REQUESTED'.",
        ]
    lines += [
        "",
        "Finish with a short summary of what you did and anything left unresolved.",
    ]
    return "\n".join(lines)


def planning_prompt(objective: str, repository_overview: str) -> str:
    return "\n".join(
        [
            "You are the planner for AgentBridge. Break the objective into a small",
            "dependency-ordered list of tasks (1-6 tasks). Do not modify any files.",
            "",
            f"Objective: {objective}",
            "",
            "Repository overview:",
            repository_overview or "(empty repository)",
            "",
            "Respond with ONLY a JSON object matching this shape:",
            json.dumps(PLAN_SCHEMA_HINT, indent=2),
        ]
    )
