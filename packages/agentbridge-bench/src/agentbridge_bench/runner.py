"""AgentBench experiment runner.

For each (task, configuration, repetition):

1. Materialise the fixture as a fresh git repo with a deterministic base commit.
2. Run setup commands and record baseline results of the visible tests.
3. Run the configuration through the real AgentBridge orchestrator.
4. Copy the hidden acceptance tests into the resulting workspace and run them.
5. Re-run visible tests to detect regressions; dry-run the merge.
6. Save a raw JSON record. Reports are derived from records only.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import platform
import re
import secrets
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agentbridge import __version__
from agentbridge.agents.capabilities import Capability
from agentbridge.agents.registry import AgentRegistry
from agentbridge.config.loader import ProjectPaths
from agentbridge.config.settings import (
    OrchestrationSettings,
    PolicyProfile,
    ProjectSettings,
    Settings,
    ValidationSettings,
)
from agentbridge.core.orchestrator import Orchestrator
from agentbridge.errors import AgentBridgeError
from agentbridge.execution.process import run_process
from agentbridge.security.permissions import check_command
from agentbridge.security.policies import build_policy
from agentbridge.storage.database import Database
from agentbridge.storage.repositories import Store
from agentbridge.tasks.models import TaskStatus
from agentbridge.validation.runners import expand
from agentbridge.workspace.conflicts import check_merge
from agentbridge_bench.dataset import (
    copy_tree,
    fixture_digest,
    materialize_fixture,
    read_overlay,
    task_dir,
)
from agentbridge_bench.models import BenchConfiguration, BenchmarkTask, ExperimentRecord
from agentbridge_bench.reports import generate_reports

ProgressFn = Callable[[str], None]
_RESULT_LINE = re.compile(r"^(PASSED|FAILED|ERROR|XPASS|XFAIL|SKIPPED)\s+(\S+)", re.MULTILINE)
_COUNTS = re.compile(r"(\d+) (passed|failed|errors?)")


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def environment_metadata() -> dict[str, Any]:
    try:
        git_version = subprocess.run(
            ["git", "--version"], capture_output=True, text=True, check=False, timeout=20
        ).stdout.strip()
    except OSError:
        git_version = None
    return {
        "agentbridge_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "git": git_version,
    }


async def _run_pytest(
    args: list[str], cwd: Path, timeout: int
) -> tuple[dict[str, str], dict[str, int], str]:
    """Run a pytest command; return (per-test outcomes, counts, output)."""
    full = expand(args)
    if "-rA" not in full and "pytest" in full:
        full = [*full, "-rA"]
    check_command(full, build_policy(PolicyProfile.STANDARD))
    result = await run_process(full, cwd=cwd, timeout=timeout)
    output = result.stdout + "\n" + result.stderr
    outcomes = {name: status for status, name in _RESULT_LINE.findall(output)}
    counts = {"passed": 0, "failed": 0}
    summary = [line for line in output.splitlines() if _COUNTS.search(line)]
    if summary:
        for number, label in _COUNTS.findall(summary[-1]):
            key = "passed" if label == "passed" else "failed"
            counts[key] += int(number)
    if result.timed_out or result.error or (not summary and result.exit_code not in (0, None)):
        # No pytest summary from a failing run (crash, missing pytest...): never report 0/0.
        counts["failed"] = max(counts["failed"], 1)
    return outcomes, counts, output


def ensure_pytest_available() -> None:
    """Hidden acceptance tests need pytest in the interpreter running AgentBench."""
    if importlib.util.find_spec("pytest") is None:
        raise AgentBridgeError(
            "AgentBench needs pytest to run the hidden acceptance tests. "
            "Install it with: pip install pytest"
        )


def _settings_for(config: BenchConfiguration, task: BenchmarkTask) -> Settings:
    return Settings(
        project=ProjectSettings(name=f"agentbench-{task.task_id}", default_branch="main"),
        orchestration=OrchestrationSettings(
            max_parallel_tasks=2,
            retry_limit=1,
            retry_backoff_seconds=1.0,
            task_timeout_seconds=task.timeout,
            planner_mode=config.planner_mode,
        ),
        providers={name: p.model_copy() for name, p in config.providers.items()},
        routing=config.routing.model_copy(),
        validation=ValidationSettings(run_lint=False, run_type_check=False, run_tests=True),
    )


async def executability(config: BenchConfiguration, settings: Settings) -> str | None:
    """Return a reason the configuration cannot run here, or None."""
    registry = AgentRegistry(settings)
    used = {
        settings.routing.planner,
        settings.routing.default_worker,
        *(settings.routing.roles.values()),
    }
    if settings.routing.reviewer:
        used.add(settings.routing.reviewer)
    for name in sorted(used):
        adapter = registry.get(name, require_enabled=False)
        caps = await adapter.get_capabilities()
        if Capability.HUMAN_IN_THE_LOOP in caps.capabilities:
            return f"provider '{name}' requires a manual remote handoff"
        report = await adapter.check_availability()
        if not report.available:
            return f"provider '{name}' unavailable: {'; '.join(report.details[:1])}"
    return None


class BenchmarkRunner:
    def __init__(
        self,
        benchmarks_dir: Path,
        output_dir: Path,
        *,
        progress: ProgressFn | None = None,
    ) -> None:
        self.benchmarks_dir = benchmarks_dir
        self.output_dir = output_dir
        self.progress = progress or (lambda _msg: None)

    async def run(
        self,
        suite_name: str,
        tasks: list[BenchmarkTask],
        configurations: list[BenchConfiguration],
        repetitions: int = 1,
        experiment_id: str | None = None,
    ) -> Path:
        ensure_pytest_available()
        experiment_id = experiment_id or (
            datetime.now(UTC).strftime("exp-%Y%m%d-%H%M%S-") + secrets.token_hex(2)
        )
        exp_dir = self.output_dir / experiment_id
        (exp_dir / "records").mkdir(parents=True, exist_ok=False)
        metadata: dict[str, Any] = {
            "experiment_id": experiment_id,
            "suite": suite_name,
            "tasks": [t.task_id for t in tasks],
            "configurations": {c.name: c.model_dump(mode="json") for c in configurations},
            "repetitions": repetitions,
            "started_at": _now(),
            **environment_metadata(),
        }
        (exp_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        for config in configurations:
            for task in tasks:
                for rep in range(1, repetitions + 1):
                    self.progress(f"{task.task_id} / {config.name} / rep {rep}")
                    record = await self.run_one(experiment_id, exp_dir, task, config, rep)
                    path = exp_dir / "records" / f"{task.task_id}__{config.name}__{rep}.json"
                    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
                    self.progress(
                        f"  -> {record.status}"
                        + (f" ({record.status_reason})" if record.status_reason else "")
                        + (
                            f", test_passed={record.test_passed}"
                            if record.status != "not_executable"
                            else ""
                        )
                    )
        metadata["finished_at"] = _now()
        (exp_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        generate_reports(exp_dir)
        return exp_dir

    async def run_one(
        self,
        experiment_id: str,
        exp_dir: Path,
        task: BenchmarkTask,
        config: BenchConfiguration,
        repetition: int,
    ) -> ExperimentRecord:
        started_at = _now()
        source = task_dir(self.benchmarks_dir, task.task_id)
        settings = _settings_for(config, task)
        base: dict[str, Any] = {
            "experiment_id": experiment_id,
            "task_id": task.task_id,
            "configuration": config.name,
            "repetition": repetition,
            "fixture_digest": fixture_digest(source / "repo"),
            "started_at": started_at,
        }
        reason = await executability(config, settings)
        if reason:
            return ExperimentRecord(
                status="not_executable", status_reason=reason, finished_at=_now(), **base
            )
        work = exp_dir / "work" / f"{task.task_id}__{config.name}__{repetition}"
        repo = work / "repo"
        try:
            base_commit = materialize_fixture(source / "repo", repo)
            for command in task.setup_commands:
                full = expand(command)
                check_command(full, build_policy(PolicyProfile.STANDARD))
                setup = await run_process(full, cwd=repo, timeout=task.timeout)
                if not setup.ok:
                    raise AgentBridgeError(f"Setup command failed: {' '.join(command)}")
            regression_cmd = task.regression_test_command
            baseline: dict[str, str] = {}
            if regression_cmd:
                baseline, _, _ = await _run_pytest(regression_cmd, repo, task.timeout)
            return await self._execute(
                task, config, settings, repo, base_commit, baseline, base, work
            )
        except AgentBridgeError as exc:
            return ExperimentRecord(
                status="error",
                status_reason=exc.message,
                finished_at=_now(),
                artifacts_dir=str(work),
                **base,
            )

    async def _execute(
        self,
        task: BenchmarkTask,
        config: BenchConfiguration,
        settings: Settings,
        repo: Path,
        base_commit: str,
        baseline: dict[str, str],
        base: dict[str, Any],
        work: Path,
    ) -> ExperimentRecord:
        paths = ProjectPaths(repo)
        db = Database(paths.database)
        store = Store(db)
        orchestrator = Orchestrator(paths, settings, store)
        metadata: dict[str, Any] = {}
        if config.oracle:
            metadata["mock_files"] = read_overlay(
                task_dir(self.benchmarks_dir, task.task_id) / "solution"
            )
        elif "mock" in settings.providers:
            metadata["mock_files"] = {"NOTES.md": "Mock control run: no real change.\n"}
        objective = (
            task.issue_description.strip()
            + "\n\nAcceptance criteria:\n"
            + "\n".join(f"- {c}" for c in task.acceptance_criteria)
        )
        started = time.monotonic()
        run_id = await orchestrator.submit(objective, metadata=metadata)
        summary = await orchestrator.execute_run(run_id)
        elapsed = round(time.monotonic() - started, 3)
        tasks = store.list_tasks(run_id=run_id)
        executions = [e for t in tasks for e in store.list_executions(t.id)]
        final = next(
            (
                t
                for t in reversed(tasks)
                if t.workspace_path and t.head_commit and t.workspace_kind == "git_worktree"
            ),
            None,
        )
        evaluation_dir = Path(final.workspace_path) if final and final.workspace_path else repo
        # Hidden acceptance tests are copied in only now, after the agent finished.
        hidden_src = task_dir(self.benchmarks_dir, task.task_id) / "hidden_tests"
        hidden_dst = evaluation_dir / "agentbench_hidden"
        copy_tree(hidden_src, hidden_dst)
        hidden_passed = hidden_failed = 0
        for command in task.test_commands:
            _, counts, output = await _run_pytest(command, evaluation_dir, task.timeout)
            hidden_passed += counts["passed"]
            hidden_failed += counts["failed"]
            (work / "hidden_tests_output.txt").write_text(output, encoding="utf-8")
        regressed: list[str] = []
        if task.regression_test_command:
            after, _, _ = await _run_pytest(
                task.regression_test_command, evaluation_dir, task.timeout
            )
            regressed = sorted(
                name
                for name, status in baseline.items()
                if (status == "PASSED" and after.get(name) not in ("PASSED", None))
                or (status == "PASSED" and name not in after)
            )
        merge_success: bool | None = None
        if final and final.git_branch:
            check = check_merge(repo, "main", final.git_branch)
            merge_success = check.clean if check.supported else None
        costs = [e.cost_usd for e in executions if e.cost_usd is not None]
        tokens_in = [e.input_tokens for e in executions if e.input_tokens is not None]
        tokens_out = [e.output_tokens for e in executions if e.output_tokens is not None]
        cost_sources = sorted({e.cost_source for e in executions if e.cost_source})
        statuses = summary.statuses
        failed = any(
            s in (TaskStatus.FAILED.value, TaskStatus.INTERRUPTED.value) for s in statuses.values()
        )
        test_passed = hidden_failed == 0 and hidden_passed > 0
        db.close()
        provider_meta: dict[str, Any] = {}
        for t in tasks:
            if t.assigned_provider:
                provider_meta.setdefault(t.assigned_provider, {"models": set()})
        for e in executions:
            if e.model:
                provider_meta.setdefault(e.provider, {"models": set()})["models"].add(e.model)
        return ExperimentRecord(
            status="failed" if failed and not test_passed else "completed",
            test_passed=test_passed,
            hidden_tests_passed=hidden_passed,
            hidden_tests_failed=hidden_failed,
            execution_time_seconds=elapsed,
            token_usage=(
                {
                    "input": sum(tokens_in) if tokens_in else None,
                    "output": sum(tokens_out) if tokens_out else None,
                }
                if tokens_in or tokens_out
                else None
            ),
            measured_cost=None,  # no billing integration: never inferred
            estimated_cost=round(sum(costs), 6) if costs else None,
            estimated_cost_source=", ".join(cost_sources) or None,
            human_interventions=sum(int(t.extra.get("human_interventions", 0)) for t in tasks),
            regression_detected=bool(regressed) if task.regression_test_command else None,
            regressed_tests=regressed,
            retries=sum(t.retry_count for t in tasks),
            merge_success=merge_success,
            validation_outcome=final.validation_outcome if final else None,
            agentbridge_task_statuses=statuses,
            base_commit=base_commit,
            providers={k: {"models": sorted(v["models"])} for k, v in provider_meta.items()},
            finished_at=_now(),
            artifacts_dir=str(work),
            **base,
        )


def run_benchmark(
    benchmarks_dir: Path,
    output_dir: Path,
    suite_name: str,
    tasks: list[BenchmarkTask],
    configurations: list[BenchConfiguration],
    repetitions: int = 1,
    progress: ProgressFn | None = None,
) -> Path:
    runner = BenchmarkRunner(benchmarks_dir, output_dir, progress=progress)
    return asyncio.run(runner.run(suite_name, tasks, configurations, repetitions))
