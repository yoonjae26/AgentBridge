"""Antigravity remote handoff: packet generation, import and local validation."""

import asyncio
import json
from pathlib import Path

import pytest

from agentbridge.agents.antigravity.adapter import sanitize_remote_url
from agentbridge.config.settings import ProviderSettings, RoutingSettings
from agentbridge.errors import InvalidStateError
from tests.conftest import git, make_settings


def remote_settings():
    return make_settings(
        providers={
            "mock": ProviderSettings(type="mock"),
            "antigravity": ProviderSettings(type="antigravity_remote", command="agy"),
        },
        routing=RoutingSettings(planner="mock", default_worker="antigravity"),
    )


def test_sanitize_remote_url():
    assert (
        sanitize_remote_url("https://user:ghp_secret@github.com/o/r.git")
        == "https://github.com/o/r.git"
    )
    assert sanitize_remote_url("git@github.com:o/r.git") == "git@github.com:o/r.git"


def test_handoff_then_import_and_approve(orchestrator_factory, repo: Path, tmp_path: Path):
    # A bare repository plays the role of the hosted remote (e.g. GitHub).
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")

    orchestrator = orchestrator_factory(remote_settings())

    async def go():
        run_id = await orchestrator.submit("Add a greeting module")
        return await orchestrator.execute_run(run_id)

    summary = asyncio.run(go())
    task = orchestrator.store.get_task(summary.task_ids[0])
    assert task.status == "WAITING_FOR_APPROVAL"
    assert task.waiting_reason == "remote_handoff"
    assert task.workspace_kind == "remote" and task.workspace_path is None
    execution = orchestrator.store.list_executions(task.id)[0]
    assert execution.status == "handoff_prepared"  # never reported as executed
    packet = json.loads(Path(task.extra["handoff_artifacts"]["packet_json"]).read_text("utf-8"))
    assert packet["repository"]["base_commit"] == task.base_commit
    assert packet["deliverables"]["result_branch"] == f"agentbridge-remote/{task.id}"
    assert "does not mean the task ran" in packet["status_note"]
    assert packet["warnings"] == []
    markdown = Path(task.extra["handoff_artifacts"]["packet_markdown"]).read_text("utf-8")
    assert "has **not** executed" in markdown

    # Merge approval is not possible before a result exists.
    with pytest.raises(InvalidStateError):
        orchestrator.approve(task.id)

    # Simulate the remote agent pushing its result branch.
    clone = tmp_path / "remote-agent"
    git(tmp_path, "clone", "-q", "-b", "main", str(remote), str(clone))
    git(clone, "config", "user.email", "agent@example.com")
    git(clone, "config", "user.name", "Remote Agent")
    git(clone, "switch", "-q", "-c", f"agentbridge-remote/{task.id}")
    (clone / "greeting.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
    git(clone, "add", "-A")
    git(clone, "commit", "-q", "-m", "remote work")
    git(clone, "push", "-q", "origin", f"agentbridge-remote/{task.id}")

    report = asyncio.run(
        orchestrator.import_remote(task.id, f"agentbridge-remote/{task.id}", "origin")
    )
    assert report.changed_files == ["greeting.py"]
    task = orchestrator.store.get_task(task.id)
    assert task.status == "WAITING_FOR_APPROVAL" and task.waiting_reason == "merge_approval"
    assert not (repo / "greeting.py").exists()
    orchestrator.approve(task.id)
    assert (repo / "greeting.py").exists()
    assert orchestrator.store.get_task(task.id).status == "SUCCEEDED"


def test_packet_warns_without_remote(orchestrator_factory):
    orchestrator = orchestrator_factory(remote_settings())

    async def go():
        run_id = await orchestrator.submit("Something")
        return await orchestrator.execute_run(run_id)

    summary = asyncio.run(go())
    task = orchestrator.store.get_task(summary.task_ids[0])
    packet = json.loads(Path(task.extra["handoff_artifacts"]["packet_json"]).read_text("utf-8"))
    assert any("not configured" in w for w in packet["warnings"])


def test_import_rejects_bad_branch_and_unrelated_history(orchestrator_factory, repo: Path):
    orchestrator = orchestrator_factory(remote_settings())

    async def go():
        run_id = await orchestrator.submit("Something")
        return await orchestrator.execute_run(run_id)

    task_id = asyncio.run(go()).task_ids[0]
    from agentbridge.errors import PolicyViolationError

    with pytest.raises(PolicyViolationError):
        asyncio.run(orchestrator.import_remote(task_id, "bad..branch"))
    # An orphan branch not descending from the base commit needs human review.
    git(repo, "switch", "-q", "--orphan", "orphan")
    (repo / "x.txt").write_text("x", encoding="utf-8")
    git(repo, "add", "x.txt")
    git(repo, "commit", "-q", "-m", "orphan")
    git(repo, "switch", "-q", "main")
    report = asyncio.run(orchestrator.import_remote(task_id, "orphan"))
    assert report.outcome.value == "NEEDS_HUMAN_REVIEW"
