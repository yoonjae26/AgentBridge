"""Dashboard API: read endpoints, token-protected actions, loopback enforcement."""

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agentbridge.config.loader import ProjectPaths
from agentbridge.dashboard.server import create_app
from tests.conftest import make_settings

BENCH = Path(__file__).resolve().parents[2] / "benchmarks"


@pytest.fixture
def setup(orchestrator_factory, repo: Path):
    orchestrator = orchestrator_factory()

    async def go():
        run_id = await orchestrator.submit("Create a hello world function")
        return await orchestrator.execute_run(run_id)

    summary = asyncio.run(go())
    app = create_app(ProjectPaths(repo), make_settings(), token="test-token", benchmarks_dir=BENCH)
    return TestClient(app), summary.task_ids[0], summary.run_id, repo


def test_read_endpoints(setup):
    client, task_id, run_id, _ = setup
    assert client.get("/api/session").json()["token"] == "test-token"
    overview = client.get("/api/overview").json()
    assert overview["waiting_for_approval"] == 1
    assert {p["name"] for p in overview["providers"]} == {"mock"}
    assert overview["recent_runs"][0]["id"] == run_id
    run = client.get(f"/api/runs/{run_id}").json()
    assert run["tasks"][0]["id"] == task_id
    tasks = client.get("/api/tasks", params={"status": "WAITING_FOR_APPROVAL"}).json()
    assert [t["id"] for t in tasks] == [task_id]
    detail = client.get(f"/api/tasks/{task_id}").json()
    assert detail["task"]["status"] == "WAITING_FOR_APPROVAL"
    assert detail["actions"] == ["approve", "reject", "cancel"]
    assert detail["validation"]["outcome"] in ("PASS", "WARNING")
    diff = client.get(f"/api/tasks/{task_id}/diff").json()
    assert diff["available"] and f"mock_outputs/{task_id}.md" in diff["patch"]
    output = client.get(f"/api/tasks/{task_id}/output").json()
    assert output["executions"][0]["status"] == "completed"
    assert client.get("/api/tasks/does-not-exist").status_code == 404


def test_actions_require_token(setup):
    client, task_id, _, repo = setup
    assert client.post(f"/api/tasks/{task_id}/approve").status_code == 403
    bad = client.post(f"/api/tasks/{task_id}/approve", headers={"X-AgentBridge-Token": "x"})
    assert bad.status_code == 403
    assert not (repo / "mock_outputs").exists()
    ok = client.post(f"/api/tasks/{task_id}/approve", headers={"X-AgentBridge-Token": "test-token"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "SUCCEEDED"
    assert (repo / "mock_outputs" / f"{task_id}.md").exists()
    again = client.post(
        f"/api/tasks/{task_id}/approve", headers={"X-AgentBridge-Token": "test-token"}
    )
    assert again.status_code == 409


def test_reject_and_cancel(setup):
    client, task_id, _, _ = setup
    headers = {"X-AgentBridge-Token": "test-token"}
    response = client.post(
        f"/api/tasks/{task_id}/reject", headers=headers, json={"reason": "not needed"}
    )
    assert response.status_code == 200
    assert client.get(f"/api/tasks/{task_id}").json()["task"]["status"] == "CANCELLED"
    assert client.post(f"/api/tasks/{task_id}/cancel", headers=headers).status_code == 409


def test_non_loopback_host_rejected(setup):
    client, *_ = setup
    response = client.get("/api/overview", headers={"Host": "evil.example.com"})
    assert response.status_code == 403


def test_benchmarks_listing(setup):
    client, *_ = setup
    experiments = client.get("/api/benchmarks").json()
    controls = [e for e in experiments if e["id"].startswith("harness-controls")]
    assert controls and controls[0]["summary"]["mock-oracle"]["task_success_rate"] == 1.0


def test_frontend_served(setup):
    client, *_ = setup
    response = client.get("/")
    assert response.status_code == 200
    assert '<div id="root">' in response.text
