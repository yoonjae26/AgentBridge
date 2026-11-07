"""Task and run reports (JSON + Markdown)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentbridge import __version__
from agentbridge.storage.database import TaskRecord, utcnow
from agentbridge.storage.repositories import Store
from agentbridge.tasks.models import TaskStatus, WaitingReason

TASK_FIELDS = (
    "id",
    "run_id",
    "project_id",
    "key",
    "title",
    "description",
    "role",
    "status",
    "priority",
    "assigned_provider",
    "routing_reason",
    "dependencies",
    "acceptance_criteria",
    "expected_files",
    "risk_level",
    "created_at",
    "started_at",
    "completed_at",
    "retry_count",
    "execution_id",
    "workspace_path",
    "workspace_kind",
    "git_branch",
    "base_branch",
    "base_commit",
    "head_commit",
    "changed_files",
    "validation_outcome",
    "waiting_reason",
    "result_summary",
    "error_message",
)


def task_dict(task: TaskRecord) -> dict[str, Any]:
    return {name: getattr(task, name) for name in TASK_FIELDS}


def next_steps(task: TaskRecord) -> list[str]:
    status = TaskStatus(task.status)
    if status is TaskStatus.WAITING_FOR_APPROVAL:
        if task.waiting_reason == WaitingReason.REMOTE_HANDOFF.value:
            return [
                "Launch the remote agent using the handoff packet, then run:",
                f"agentbridge remote import {task.id} --branch agentbridge-remote/{task.id}",
            ]
        return [
            f"Inspect the changes: git diff {(task.base_commit or '')[:12]} {task.git_branch}",
            f"Approve and merge: agentbridge tasks approve {task.id}",
            f"Reject (keeps the branch): agentbridge tasks reject {task.id}",
        ]
    if status in (TaskStatus.INTERRUPTED, TaskStatus.FAILED):
        return [
            f"Inspect: agentbridge tasks inspect {task.id}",
            f"Resume: agentbridge tasks resume {task.id}",
        ]
    return []


def build_task_report(store: Store, task_id: str) -> dict[str, Any]:
    task = store.get_task(task_id)
    executions = [
        {
            "execution_id": e.id,
            "provider": e.provider,
            "attempt": e.attempt,
            "status": e.status,
            "started_at": e.started_at,
            "finished_at": e.finished_at,
            "duration_seconds": e.duration_seconds,
            "exit_code": e.exit_code,
            "model": e.model,
            "input_tokens": e.input_tokens,
            "output_tokens": e.output_tokens,
            "cost_usd": e.cost_usd,
            "cost_source": e.cost_source,
            "summary": e.summary,
            "error": e.error,
            "output_path": e.output_path,
        }
        for e in store.list_executions(task_id)
    ]
    validations = store.list_validations(task_id)
    latest_validation = validations[-1].data if validations else None
    events = [
        {
            "at": ev.created_at,
            "type": ev.type,
            "from": ev.from_status,
            "to": ev.to_status,
            "message": ev.message,
        }
        for ev in store.list_events(task_id=task_id)
    ]
    return {
        "report_version": 1,
        "generated_at": utcnow(),
        "agentbridge_version": __version__,
        "task": task_dict(task),
        "executions": executions,
        "validation": latest_validation,
        "validation_attempts": len(validations),
        "events": events,
        "next_steps": next_steps(task),
        "notes": [
            "Agent statements are not trusted; the validation section reflects checks "
            "AgentBridge ran itself.",
            "Unavailable metrics are reported as null, never as zero.",
        ],
    }


def _fmt(value: Any) -> str:
    return "n/a" if value is None else str(value)


def render_task_markdown(report: dict[str, Any]) -> str:
    task = report["task"]
    lines = [
        f"# AgentBridge task report: {task['id']}",
        "",
        f"- **Title:** {task['title']}",
        f"- **Status:** `{task['status']}`"
        + (f" ({task['waiting_reason']})" if task.get("waiting_reason") else ""),
        f"- **Role:** {task['role']}",
        f"- **Provider:** {_fmt(task['assigned_provider'])}",
        f"- **Routing:** {_fmt(task['routing_reason'])}",
        f"- **Workspace:** {_fmt(task['workspace_path'])} ({_fmt(task['workspace_kind'])})",
        f"- **Branch:** {_fmt(task['git_branch'])} (base {_fmt(task['base_branch'])} "
        f"@ {_fmt((task['base_commit'] or '')[:12] or None)})",
        f"- **Retries:** {task['retry_count']}",
        f"- **Validation:** {_fmt(task['validation_outcome'])}",
        f"- **Generated:** {report['generated_at']} (AgentBridge {report['agentbridge_version']})",
        "",
    ]
    if task.get("acceptance_criteria"):
        lines += ["## Acceptance criteria", ""]
        lines += [f"- {c}" for c in task["acceptance_criteria"]] + [""]
    if task.get("result_summary"):
        lines += [
            "## Agent summary (unverified)",
            "",
            "```text",
            task["result_summary"][-3000:],
            "```",
            "",
        ]
    if task.get("error_message"):
        lines += ["## Error", "", "```text", task["error_message"][-2000:], "```", ""]
    lines += ["## Executions", ""]
    if report["executions"]:
        lines += [
            "| Attempt | Provider | Status | Duration (s) | Exit | Tokens in/out | Cost (USD) |",
            "|---|---|---|---|---|---|---|",
        ]
        for e in report["executions"]:
            cost = _fmt(e["cost_usd"])
            if e["cost_usd"] is not None and e["cost_source"]:
                cost += f" ({e['cost_source']})"
            lines.append(
                f"| {e['attempt']} | {e['provider']} | {e['status']} | "
                f"{_fmt(e['duration_seconds'])} | {_fmt(e['exit_code'])} | "
                f"{_fmt(e['input_tokens'])}/{_fmt(e['output_tokens'])} | {cost} |"
            )
    else:
        lines.append("No executions recorded.")
    lines.append("")
    validation = report.get("validation")
    lines += ["## Validation", ""]
    if validation:
        lines += [
            f"Overall: **{validation['outcome']}**",
            "",
            "| Step | Outcome | Summary | Command | Exit | Duration (s) |",
            "|---|---|---|---|---|---|",
        ]
        for step in validation["steps"]:
            command = " ".join(step["command"][1:] if step.get("command") else []) or "-"
            summary = str(step.get("summary", "")).replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {step['name']} | {step['outcome']} | {summary[:120]} | `{command[:60]}` | "
                f"{_fmt(step.get('exit_code'))} | {_fmt(step.get('duration_seconds'))} |"
            )
        if validation.get("changed_files"):
            lines += ["", "Changed files:", ""]
            lines += [f"- `{p}`" for p in validation["changed_files"]]
        findings = next(
            (s["details"].get("findings") for s in validation["steps"] if s["name"] == "review"),
            None,
        )
        if findings:
            lines += ["", "Review findings:", ""]
            lines += [
                f"- [{f['severity']}] {f['message']} ({f.get('path') or '-'})" for f in findings
            ]
    else:
        lines.append("Validation has not run.")
    lines.append("")
    if report["next_steps"]:
        lines += (
            ["## Next steps", ""]
            + [
                f"- `{s}`" if s.startswith("agentbridge") or s.startswith("git") else f"- {s}"
                for s in report["next_steps"]
            ]
            + [""]
        )
    lines += [
        "## Event history",
        "",
        "| Time | Event | Transition | Message |",
        "|---|---|---|---|",
    ]
    for ev in report["events"]:
        transition = f"{ev['from'] or ''} -> {ev['to']}" if ev["to"] else ""
        message = str(ev["message"]).replace("|", "\\|").replace("\n", " ")[:160]
        lines.append(f"| {ev['at']} | {ev['type']} | {transition} | {message} |")
    lines += ["", "---", *[f"_{n}_" for n in report["notes"]], ""]
    return "\n".join(lines)


def write_task_report(store: Store, task_id: str, reports_dir: Path) -> tuple[Path, Path]:
    report = build_task_report(store, task_id)
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"{task_id}.json"
    md_path = reports_dir / f"{task_id}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path.write_text(render_task_markdown(report), encoding="utf-8")
    return json_path, md_path


def write_run_report(store: Store, run_id: str, reports_dir: Path) -> tuple[Path, Path]:
    run = store.get_run(run_id)
    tasks = store.list_tasks(run_id=run_id)
    task_reports = [build_task_report(store, t.id) for t in tasks]
    report = {
        "report_version": 1,
        "generated_at": utcnow(),
        "agentbridge_version": __version__,
        "run": {
            "id": run.id,
            "objective": run.objective,
            "planner": run.planner,
            "policy": run.policy,
            "base_branch": run.base_branch,
            "base_commit": run.base_commit,
            "created_at": run.created_at,
            "plan_warnings": run.warnings,
        },
        "tasks": task_reports,
    }
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / f"{run_id}.json"
    md_path = reports_dir / f"{run_id}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    lines = [
        f"# AgentBridge run report: {run.id}",
        "",
        f"- **Objective:** {run.objective}",
        f"- **Planner:** {run.planner}",
        f"- **Policy:** {run.policy}",
        f"- **Base:** {run.base_branch} @ {(run.base_commit or '')[:12]}",
        "",
        "| Task | Role | Status | Provider | Validation |",
        "|---|---|---|---|---|",
    ]
    for t in tasks:
        lines.append(
            f"| {t.id} | {t.role} | {t.status} | {_fmt(t.assigned_provider)} | "
            f"{_fmt(t.validation_outcome)} |"
        )
    if run.warnings:
        lines += ["", "## Plan warnings", ""] + [f"- {w}" for w in run.warnings]
    lines += ["", "Per-task reports:", ""] + [f"- `{t.id}.md`" for t in tasks] + [""]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
