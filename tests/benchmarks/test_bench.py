import asyncio
import json
from pathlib import Path

import pytest

from agentbridge_bench.dataset import (
    fixture_digest,
    load_configurations,
    load_suites,
    load_tasks,
    materialize_fixture,
    task_dir,
)
from agentbridge_bench.models import TaskCategory
from agentbridge_bench.reports import generate_reports
from agentbridge_bench.runner import BenchmarkRunner

BENCH = Path(__file__).resolve().parents[2] / "benchmarks"


def test_dataset_is_complete():
    tasks = load_tasks(BENCH)
    assert len(tasks) >= 10
    assert {t.task_category for t in tasks.values()} == set(TaskCategory)
    for task in tasks.values():
        directory = task_dir(BENCH, task.task_id)
        assert (directory / "repo").is_dir()
        assert list((directory / "hidden_tests").glob("test_*.py"))
        assert (directory / "solution").is_dir()
        assert task.acceptance_criteria and task.test_commands
    suites = load_suites(BENCH, tasks)
    assert set(suites["core"]) == set(tasks)


def test_configurations_load():
    configs = load_configurations(BENCH)
    assert {
        "mock-oracle",
        "mock-noop",
        "claude-single",
        "claude-multi",
        "antigravity-remote",
    } <= set(configs)


def test_fixture_commit_is_deterministic(tmp_path: Path):
    source = task_dir(BENCH, "bugfix-001") / "repo"
    first = materialize_fixture(source, tmp_path / "a")
    second = materialize_fixture(source, tmp_path / "b")
    assert first == second
    assert fixture_digest(source) == fixture_digest(tmp_path / "a")


@pytest.mark.integration
def test_controls_and_reproducible_reports(tmp_path: Path):
    tasks = load_tasks(BENCH)
    configs = load_configurations(BENCH)
    selected = [tasks["bugfix-002"], tasks["tests-001"]]
    runner = BenchmarkRunner(BENCH, tmp_path)
    exp_dir = asyncio.run(
        runner.run(
            "test",
            selected,
            [configs["mock-oracle"], configs["mock-noop"], configs["antigravity-remote"]],
            experiment_id="exp-test",
        )
    )
    summary = json.loads((exp_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["mock-oracle"]["task_success_rate"] == 1.0
    assert summary["mock-noop"]["task_success_rate"] == 0.0
    assert summary["antigravity-remote"]["runs_executed"] == 0
    assert summary["antigravity-remote"]["task_success_rate"] is None
    record = json.loads(
        (exp_dir / "records" / "bugfix-002__mock-oracle__1.json").read_text(encoding="utf-8")
    )
    assert record["token_usage"] is None and record["measured_cost"] is None
    assert record["regression_detected"] is False and record["merge_success"] is True
    for name in (
        "records.csv",
        "summary.csv",
        "report.md",
        "success_rate.svg",
        "execution_time.svg",
        "metadata.json",
    ):
        assert (exp_dir / name).exists(), name
    # Reports are reproducible from saved records alone.
    assert generate_reports(exp_dir) == summary


def test_missing_pytest_is_an_error_not_zero_tests(monkeypatch):
    import importlib.util

    import pytest

    from agentbridge.errors import AgentBridgeError
    from agentbridge_bench import runner

    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    with pytest.raises(AgentBridgeError, match="pytest"):
        runner.ensure_pytest_available()


def test_failing_run_without_summary_counts_as_failure(tmp_path):
    import asyncio
    import sys

    from agentbridge_bench.runner import _run_pytest

    _, counts, _ = asyncio.run(
        _run_pytest([sys.executable, "-m", "pytest", "--no-such-option"], tmp_path, 60)
    )
    assert counts["failed"] >= 1
