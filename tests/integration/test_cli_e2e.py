"""End-to-end through the real CLI (Typer runner) with the mock provider."""

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from agentbridge.cli.app import app
from tests.conftest import git

runner = CliRunner()

EMAIL_MODULE = '''"""Validators."""

import re

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\\.[A-Za-z0-9-]+)*\\.[A-Za-z]{2,}")


def is_valid_email(address: str) -> bool:
    """Return True if address looks like a valid e-mail address."""
    return bool(_EMAIL.fullmatch(address))
'''

EMAIL_TESTS = """from validators import is_valid_email


def test_valid():
    assert is_valid_email("user@example.com")


def test_invalid():
    assert not is_valid_email("not-an-email")
"""


def invoke(args, cwd: Path, monkeypatch):
    monkeypatch.chdir(cwd)
    return runner.invoke(app, args, catch_exceptions=False)


def test_first_milestone_workflow(repo: Path, monkeypatch):
    result = invoke(["init"], repo, monkeypatch)
    assert result.exit_code == 0, result.output
    assert (repo / "agentbridge.yaml").exists()

    result = invoke(["providers", "list"], repo, monkeypatch)
    assert result.exit_code == 0 and "mock" in result.output

    result = invoke(
        ["run", "Create a Python hello world function", "--provider", "mock", "--json"],
        repo,
        monkeypatch,
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    task_id = next(iter(payload["tasks"]))
    assert payload["tasks"][task_id] == "WAITING_FOR_APPROVAL"

    result = invoke(["tasks", "list", "--json"], repo, monkeypatch)
    assert result.exit_code == 0
    assert json.loads(result.output)[0]["id"] == task_id

    result = invoke(["report", task_id, "--format", "json"], repo, monkeypatch)
    assert result.exit_code == 0
    report_path = repo / ".agentbridge" / "reports" / f"{task_id}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["task"]["status"] == "WAITING_FOR_APPROVAL"
    assert report["validation"]["outcome"] in ("PASS", "WARNING")
    assert report["executions"][0]["provider"] == "mock"
    assert (repo / ".agentbridge" / "reports" / f"{task_id}.md").exists()

    for args in (["tasks", "status", task_id], ["tasks", "inspect", task_id], ["logs", task_id]):
        assert invoke(args, repo, monkeypatch).exit_code == 0


def test_email_validator_scenario(repo: Path, monkeypatch):
    """The specification's end-to-end scenario (with a deterministic mock agent)."""
    assert invoke(["init"], repo, monkeypatch).exit_code == 0
    config = yaml.safe_load((repo / "agentbridge.yaml").read_text(encoding="utf-8"))
    config["providers"]["mock"]["files"] = {
        "validators.py": EMAIL_MODULE,
        "tests/test_validators.py": EMAIL_TESTS,
    }
    config["validation"]["run_type_check"] = False
    (repo / "agentbridge.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    git(repo, "add", "agentbridge.yaml")
    git(repo, "commit", "-q", "-m", "configure agentbridge")
    head_before = git(repo, "rev-parse", "HEAD")

    objective = (
        "Add a function that validates email addresses. Write unit tests. "
        "Run all checks. Generate a final report."
    )
    result = invoke(["run", objective, "--provider", "mock", "--json"], repo, monkeypatch)
    assert result.exit_code == 0, result.output
    task_id = next(iter(json.loads(result.output)["tasks"]))

    report = json.loads(invoke(["tasks", "inspect", task_id], repo, monkeypatch).output)
    task = report["task"]
    # 1-2: task created, worktree prepared
    assert task["workspace_kind"] == "git_worktree"
    worktree = Path(task["workspace_path"])
    assert worktree.is_dir() and worktree != repo
    # 3-4: agent executed and modified files
    assert report["executions"][0]["status"] == "completed"
    assert sorted(task["changed_files"]) == ["tests/test_validators.py", "validators.py"]
    # 5-6: tests ran independently and results were captured
    steps = {s["name"]: s for s in report["validation"]["steps"]}
    assert steps["tests"]["outcome"] == "PASS"
    assert steps["tests"]["details"]["passed"] == 2
    assert steps["lint"]["outcome"] == "PASS"
    # 7: report generated
    assert (repo / ".agentbridge" / "reports" / f"{task_id}.md").exists()
    # 8: isolated until approval
    assert git(repo, "rev-parse", "HEAD") == head_before
    assert not (repo / "validators.py").exists()

    result = invoke(["tasks", "approve", task_id], repo, monkeypatch)
    assert result.exit_code == 0, result.output
    assert (repo / "validators.py").exists()
    assert git(repo, "rev-parse", "HEAD") != head_before


def test_exit_codes(repo: Path, monkeypatch, tmp_path: Path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert invoke(["tasks", "list"], outside, monkeypatch).exit_code == 2  # no config
    assert invoke(["init"], repo, monkeypatch).exit_code == 0
    assert invoke(["tasks", "status", "nope"], repo, monkeypatch).exit_code == 5
    failed = invoke(
        ["run", "x", "--provider", "mock", "--mock-scenario", "invalid_output"], repo, monkeypatch
    )
    assert failed.exit_code == 1
    unknown = invoke(["run", "x", "--provider", "ghost"], repo, monkeypatch)
    assert unknown.exit_code == 1  # task failed: provider not configured
    assert invoke(["--version"], repo, monkeypatch).exit_code == 0
