"""Loading benchmark tasks/configurations and materialising fixture repositories."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

import yaml
from pydantic import ValidationError

from agentbridge.errors import ConfigError, NotFoundError
from agentbridge.workspace.git import Git
from agentbridge_bench.models import BenchConfiguration, BenchmarkTask

FIXED_DATE = "2025-01-01T00:00:00+00:00"


def default_benchmarks_dir() -> Path:
    env = os.environ.get("AGENTBENCH_DIR")
    if env:
        return Path(env)
    cwd_candidate = Path.cwd() / "benchmarks"
    if (cwd_candidate / "tasks").is_dir():
        return cwd_candidate
    # Source checkout: <repo>/packages/agentbridge-bench/src/agentbridge_bench/dataset.py
    checkout = Path(__file__).resolve().parents[4] / "benchmarks"
    if (checkout / "tasks").is_dir():
        return checkout
    # Installed wheel: the task suite ships inside the package.
    return Path(__file__).resolve().parent / "data"


def _read_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc


def load_tasks(benchmarks_dir: Path) -> dict[str, BenchmarkTask]:
    tasks_dir = benchmarks_dir / "tasks"
    if not tasks_dir.is_dir():
        raise NotFoundError(f"No benchmark tasks directory at {tasks_dir}")
    tasks: dict[str, BenchmarkTask] = {}
    for task_file in sorted(tasks_dir.glob("*/task.yaml")):
        try:
            task = BenchmarkTask.model_validate(_read_yaml(task_file))
        except ValidationError as exc:
            raise ConfigError(f"Invalid benchmark task {task_file}: {exc}") from exc
        if task.task_id != task_file.parent.name:
            raise ConfigError(f"{task_file}: task_id must match its directory name")
        tasks[task.task_id] = task
    return tasks


def load_configurations(benchmarks_dir: Path) -> dict[str, BenchConfiguration]:
    data = _read_yaml(benchmarks_dir / "configurations.yaml")
    if not isinstance(data, dict) or not isinstance(data.get("configurations"), dict):
        raise ConfigError("configurations.yaml must contain a 'configurations' mapping")
    result = {}
    for name, raw in data["configurations"].items():
        try:
            config = BenchConfiguration.model_validate({**raw, "name": name})
        except ValidationError as exc:
            raise ConfigError(f"Invalid benchmark configuration {name!r}: {exc}") from exc
        result[name] = config
    return result


def load_suites(benchmarks_dir: Path, tasks: dict[str, BenchmarkTask]) -> dict[str, list[str]]:
    suites: dict[str, list[str]] = {"all": sorted(tasks)}
    path = benchmarks_dir / "suites.yaml"
    if path.exists():
        data = _read_yaml(path)
        if isinstance(data, dict):
            for name, ids in (data.get("suites") or {}).items():
                unknown = [i for i in ids if i not in tasks]
                if unknown:
                    raise ConfigError(f"Suite {name!r} references unknown tasks: {unknown}")
                suites[name] = list(ids)
    return suites


def task_dir(benchmarks_dir: Path, task_id: str) -> Path:
    return benchmarks_dir / "tasks" / task_id


_IGNORED_PARTS = frozenset({"__pycache__", ".pytest_cache", ".git", ".agentbridge"})


def _iter_files(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.rglob("*")
        if p.is_file() and not _IGNORED_PARTS.intersection(p.relative_to(root).parts)
    )


def read_overlay(directory: Path) -> dict[str, str]:
    """Files of a solution overlay as {relative posix path: content (LF)}."""
    if not directory.is_dir():
        return {}
    return {
        p.relative_to(directory).as_posix(): p.read_text(encoding="utf-8").replace("\r\n", "\n")
        for p in _iter_files(directory)
    }


def fixture_digest(repo_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in _iter_files(repo_dir):
        digest.update(path.relative_to(repo_dir).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
        digest.update(b"\0")
    return digest.hexdigest()


def materialize_fixture(source: Path, target: Path) -> str:
    """Copy a fixture into ``target`` as a fresh git repo with a deterministic commit.

    Line endings are normalised to LF and author/committer/date are fixed, so the
    same fixture content always yields the same base commit hash.
    """
    if target.exists():
        raise ConfigError(f"Benchmark workspace already exists: {target}")
    target.mkdir(parents=True)
    for path in _iter_files(source):
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    git = Git(target)
    git.run("init", "-q", "-b", "main")
    git.run("config", "core.autocrlf", "false")
    git.run("config", "user.name", "AgentBench")
    git.run("config", "user.email", "agentbench@localhost")
    git.run("config", "commit.gpgsign", "false")
    git.run("add", "-A")
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_DATE=FIXED_DATE,
        GIT_COMMITTER_DATE=FIXED_DATE,
        GIT_AUTHOR_NAME="AgentBench",
        GIT_AUTHOR_EMAIL="agentbench@localhost",
        GIT_COMMITTER_NAME="AgentBench",
        GIT_COMMITTER_EMAIL="agentbench@localhost",
    )
    git.run("commit", "-q", "-m", "AgentBench fixture base", env=env)
    return git.head()


def copy_tree(source: Path, target: Path) -> None:
    for path in _iter_files(source):
        destination = target / path.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
