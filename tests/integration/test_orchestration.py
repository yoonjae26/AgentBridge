"""Orchestrator behaviour with the mock provider: scheduling, recovery, approval."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from agentbridge.config.settings import OrchestrationSettings, ProviderSettings, RoutingSettings
from agentbridge.errors import InvalidStateError
from agentbridge.tasks.models import TaskStatus
from tests.conftest import git, make_settings


def run(orchestrator, objective, **kw):
    async def go():
        run_id = await orchestrator.submit(objective, **kw)
        return await orchestrator.execute_run(run_id)

    return asyncio.run(go())


def test_mock_task_end_to_end(orchestrator_factory, repo: Path):
    orchestrator = orchestrator_factory()
    summary = run(orchestrator, "Create a Python hello world function")
    task = orchestrator.store.get_task(summary.task_ids[0])
    assert task.status == "WAITING_FOR_APPROVAL"
    assert task.waiting_reason == "merge_approval"
    assert task.changed_files == [f"mock_outputs/{task.id}.md"]
    statuses = [e.to_status for e in orchestrator.store.list_events(task_id=task.id) if e.to_status]
    assert statuses == [
        "PENDING",
        "READY",
        "QUEUED",
        "RUNNING",
        "VALIDATING",
        "WAITING_FOR_APPROVAL",
    ]
    assert not (repo / "mock_outputs").exists()  # isolated until approval
    assert (orchestrator.paths.reports_dir / f"{task.id}.md").exists()
    message = orchestrator.approve(task.id)
    assert "Merged" in message
    assert (repo / "mock_outputs" / f"{task.id}.md").exists()
    assert orchestrator.store.get_task(task.id).status == "SUCCEEDED"


def test_standard_plan_respects_dependencies(orchestrator_factory):
    orchestrator = orchestrator_factory()
    summary = run(orchestrator, "Add a feature", planner_mode="standard")
    tasks = orchestrator.store.list_tasks(run_id=summary.run_id)
    by_key = {t.key: t for t in tasks}
    assert by_key["task-001"].status == "SUCCEEDED"  # analysis: no changes to merge
    assert by_key["task-002"].status == "WAITING_FOR_APPROVAL"
    assert by_key["task-003"].status == "SUCCEEDED"  # review verdict PASS, no changes
    # Ordering: each task started only after its dependency left the active states.
    events = orchestrator.store.list_events(run_id=summary.run_id)
    order = [e.task_id for e in events if e.to_status == "RUNNING"]
    assert order == [by_key["task-001"].id, by_key["task-002"].id, by_key["task-003"].id]
    # The reviewer worked on top of the developer's branch.
    review_ws = Path(by_key["task-003"].workspace_path or "")
    assert (review_ws / "mock_outputs" / f"{by_key['task-002'].id}.md").exists()


def test_provider_planner_mode(orchestrator_factory):
    orchestrator = orchestrator_factory()
    summary = run(orchestrator, "Build it", planner_mode="provider")
    assert len(summary.task_ids) == 3


def test_failed_dependency_fails_downstream(orchestrator_factory):
    settings = make_settings(
        providers={
            "mock": ProviderSettings(type="mock"),
            "broken": ProviderSettings(type="mock", scenario="failure"),
        },
        routing=RoutingSettings(roles={"analyst": "broken"}),
        orchestration=OrchestrationSettings(retry_limit=0, heartbeat_seconds=0.05),
    )
    orchestrator = orchestrator_factory(settings)
    summary = run(orchestrator, "Add a feature", planner_mode="standard")
    statuses = sorted(summary.statuses.values())
    assert statuses == ["FAILED", "FAILED", "FAILED"]


def test_interrupted_execution_and_safe_resume(orchestrator_factory):
    settings = make_settings(
        providers={"mock": ProviderSettings(type="mock", scenario="interrupt")}
    )
    orchestrator = orchestrator_factory(settings)
    summary = run(orchestrator, "Do work")
    task_id = summary.task_ids[0]
    assert orchestrator.store.get_task(task_id).status == "INTERRUPTED"
    # No work in the workspace and an uncertain outcome: refuse to re-run silently.
    with pytest.raises(InvalidStateError, match="may or may not") as info:
        asyncio.run(orchestrator.resume(task_id))
    assert "--rerun" in (info.value.hint or "")
    assert len(orchestrator.store.list_executions(task_id)) == 1


def test_resume_validates_existing_work_without_rerunning(orchestrator_factory):
    settings = make_settings(
        providers={"mock": ProviderSettings(type="mock", scenario="interrupt")}
    )
    orchestrator = orchestrator_factory(settings)
    summary = run(orchestrator, "Do work")
    task = orchestrator.store.get_task(summary.task_ids[0])
    # The agent had written a file before the process died.
    (Path(task.workspace_path or "") / "partial.py").write_text("X = 1\n", encoding="utf-8")
    status = asyncio.run(orchestrator.resume(task.id))
    assert status == "WAITING_FOR_APPROVAL"
    assert len(orchestrator.store.list_executions(task.id)) == 1  # not re-executed
    assert orchestrator.store.get_task(task.id).changed_files == ["partial.py"]


def test_explicit_rerun(orchestrator_factory):
    orchestrator = orchestrator_factory(
        make_settings(providers={"mock": ProviderSettings(type="mock", scenario="interrupt")})
    )
    summary = run(orchestrator, "Do work")
    task_id = summary.task_ids[0]
    orchestrator.settings.providers["mock"].scenario = "success"
    orchestrator.registry.get("mock").settings.scenario = "success"
    status = asyncio.run(orchestrator.resume(task_id, rerun=True))
    assert status == "WAITING_FOR_APPROVAL"
    assert len(orchestrator.store.list_executions(task_id)) == 2


def test_startup_recovery_marks_orphans_interrupted(orchestrator_factory):
    settings = make_settings(
        orchestration=OrchestrationSettings(stale_after_seconds=1, heartbeat_seconds=0.05)
    )
    orchestrator = orchestrator_factory(settings)
    run_id = asyncio.run(orchestrator.submit("Do work"))
    task_id = f"{run_id}-task-001"
    store = orchestrator.store
    for status in (TaskStatus.READY, TaskStatus.QUEUED, TaskStatus.RUNNING):
        store.transition(task_id, status)
    stale = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    store.update_task(task_id, execution_id=f"{task_id}-a1", assigned_provider="mock")
    with store.db.session() as session, session.begin():
        from agentbridge.storage.database import TaskRecord

        session.get(TaskRecord, task_id).heartbeat_at = stale  # type: ignore[union-attr]
        session.get(TaskRecord, task_id).updated_at = stale  # type: ignore[union-attr]
    recovered = orchestrator.recover()
    assert recovered == [task_id]
    assert store.get_task(task_id).status == "INTERRUPTED"


def test_cancel_pending_and_running(orchestrator_factory):
    settings = make_settings(
        providers={"mock": ProviderSettings(type="mock", scenario="delay", delay_seconds=30)}
    )
    orchestrator = orchestrator_factory(settings)

    async def go():
        run_id = await orchestrator.submit("Slow work")
        task_id = f"{run_id}-task-001"
        runner = asyncio.create_task(orchestrator.execute_run(run_id))
        for _ in range(100):
            await asyncio.sleep(0.05)
            if orchestrator.store.get_task(task_id).status == "RUNNING":
                break
        message = orchestrator.request_cancel(task_id)
        await asyncio.wait_for(runner, timeout=10)
        return task_id, message

    task_id, message = asyncio.run(go())
    assert "requested" in message
    assert orchestrator.store.get_task(task_id).status == "CANCELLED"


def test_reject_keeps_branch(orchestrator_factory, repo: Path):
    orchestrator = orchestrator_factory()
    summary = run(orchestrator, "Change things")
    task = orchestrator.store.get_task(summary.task_ids[0])
    orchestrator.reject(task.id)
    assert orchestrator.store.get_task(task.id).status == "CANCELLED"
    assert task.git_branch in git(repo, "branch", "--list", task.git_branch or "")


def test_approve_requires_clean_primary_checkout(orchestrator_factory, repo: Path):
    orchestrator = orchestrator_factory()
    summary = run(orchestrator, "Change things")
    task_id = summary.task_ids[0]
    (repo / "README.md").write_text("my unsaved work\n", encoding="utf-8")
    with pytest.raises(InvalidStateError, match="uncommitted"):
        orchestrator.approve(task_id)
    assert orchestrator.store.get_task(task_id).status == "WAITING_FOR_APPROVAL"
    assert (repo / "README.md").read_text(encoding="utf-8") == "my unsaved work\n"
