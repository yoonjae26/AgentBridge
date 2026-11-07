import asyncio
from pathlib import Path

from agentbridge.config.settings import OrchestrationSettings, ProviderSettings
from agentbridge.security.paths import slugify
from agentbridge.workspace.manager import WorkspaceManager
from tests.conftest import make_settings


def test_retry_with_exponential_backoff(orchestrator_factory):
    delays: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        delays.append(seconds)

    settings = make_settings(
        providers={"mock": ProviderSettings(type="mock", scenario="failure")},
        orchestration=OrchestrationSettings(
            retry_limit=2, retry_backoff_seconds=1.5, heartbeat_seconds=0.05
        ),
    )
    orchestrator = orchestrator_factory(settings, sleep=fake_sleep)

    async def go():
        run_id = await orchestrator.submit("Do something")
        return await orchestrator.execute_run(run_id)

    summary = asyncio.run(go())
    task = orchestrator.store.get_task(summary.task_ids[0])
    assert task.status == "FAILED"
    assert task.retry_count == 2
    assert delays == [1.5, 3.0]
    assert len(orchestrator.store.list_executions(task.id)) == 3


def test_non_retryable_failure_is_not_retried(orchestrator_factory):
    settings = make_settings(
        providers={"mock": ProviderSettings(type="mock", scenario="invalid_output")}
    )
    orchestrator = orchestrator_factory(settings)

    async def go():
        run_id = await orchestrator.submit("Do something")
        return await orchestrator.execute_run(run_id)

    summary = asyncio.run(go())
    task = orchestrator.store.get_task(summary.task_ids[0])
    assert task.status == "FAILED"
    assert task.retry_count == 0


def test_slugify():
    assert slugify("Add OAuth2 login!!") == "add-oauth2-login"
    assert slugify("") == "task"
    assert len(slugify("x" * 200, 40)) == 40


def test_branch_naming(repo: Path):
    manager = WorkspaceManager(repo, repo / ".agentbridge" / "worktrees", "agentbridge")
    branch = manager.branch_name("r1a2b3-task-001", "Implement the auth model")
    assert branch == "agentbridge/r1a2b3-task-001-implement-the-auth-model"
    weird = manager.branch_name("r1a2b3-task-002", "..//~^:?*[")
    assert weird.startswith("agentbridge/r1a2b3-task-002")
