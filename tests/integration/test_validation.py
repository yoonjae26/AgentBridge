import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from agentbridge.config.settings import PolicyProfile, ValidationSettings
from agentbridge.security.policies import build_policy
from agentbridge.validation.engine import ValidationEngine
from agentbridge.validation.models import Outcome
from agentbridge.validation.runners import parse_pytest_counts
from agentbridge.workspace.manager import WorkspaceManager

GOOD_TEST = "from calc import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"


def setup_workspace(repo: Path, files: dict[str, str]):
    manager = WorkspaceManager(repo, repo / ".agentbridge" / "worktrees", "agentbridge")
    ws = manager.create_worktree("r1-task-001", "Work")
    for name, content in files.items():
        path = ws.path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    manager.commit_changes(ws.path, "work")
    return ws


def engine(**kw):
    settings = ValidationSettings(run_type_check=False, **kw)
    return ValidationEngine(settings, build_policy(PolicyProfile.STANDARD))


def test_passing_change(repo: Path):
    ws = setup_workspace(
        repo, {"calc.py": "def add(a, b):\n    return a + b\n", "tests/test_calc.py": GOOD_TEST}
    )
    report = asyncio.run(engine().validate(ws.path, ws.base_commit or ""))
    assert report.outcome is Outcome.PASS, report.model_dump()
    assert report.tests_passed == 1 and report.tests_failed == 0
    tests = report.step("tests")
    assert tests is not None and tests.command and tests.exit_code == 0
    assert tests.duration_seconds is not None


def test_failing_tests_fail_validation(repo: Path):
    ws = setup_workspace(
        repo, {"calc.py": "def add(a, b):\n    return a - b\n", "tests/test_calc.py": GOOD_TEST}
    )
    report = asyncio.run(engine().validate(ws.path, ws.base_commit or ""))
    assert report.outcome is Outcome.FAIL
    assert report.tests_failed == 1


def test_lint_failure_detected(repo: Path):
    ws = setup_workspace(repo, {"calc.py": "import os\ndef add(a, b):\n    return a + b\n"})
    report = asyncio.run(engine(run_tests=False).validate(ws.path, ws.base_commit or ""))
    lint = report.step("lint")
    assert lint is not None and lint.outcome is Outcome.FAIL


def test_scope_violation_needs_review(repo: Path):
    ws = setup_workspace(repo, {"src/a.py": "A = 1\n", "other/b.py": "B = 2\n"})
    report = asyncio.run(
        engine(run_tests=False, run_lint=False).validate(
            ws.path, ws.base_commit or "", expected_files=["src"]
        )
    )
    assert report.outcome is Outcome.NEEDS_HUMAN_REVIEW
    scope = report.step("scope")
    assert scope is not None and scope.details["outside_scope"] == ["other/b.py"]


def test_no_tests_is_a_warning(repo: Path):
    ws = setup_workspace(repo, {"notes.md": "hello\n"})
    report = asyncio.run(engine(run_lint=False).validate(ws.path, ws.base_commit or ""))
    assert report.outcome is Outcome.WARNING
    tests = report.step("tests")
    assert tests is not None and tests.exit_code == 5


def test_policy_blocks_configured_command(repo: Path):
    ws = setup_workspace(repo, {"a.txt": "x\n"})
    eng = engine(run_lint=False, test_command=["bash", "-c", "true"])
    report = asyncio.run(eng.validate(ws.path, ws.base_commit or ""))
    tests = report.step("tests")
    assert tests is not None and tests.outcome is Outcome.FAIL
    assert "policy" in tests.summary


def test_parse_pytest_counts():
    assert parse_pytest_counts("==== 3 passed, 1 failed, 2 errors in 0.1s ====") == {
        "passed": 3,
        "failed": 1,
        "errors": 2,
    }
    assert parse_pytest_counts("nothing") == {}


# ------------------------------------------------------------ docker sandbox
def test_docker_wrapper_is_locked_down(tmp_path: Path):
    from agentbridge.config.settings import DockerSandboxSettings
    from agentbridge.execution.sandbox import expand_for_container, wrap_command

    inner = expand_for_container(["{python}", "-m", "pytest", "-q"])
    args = wrap_command(inner, tmp_path, DockerSandboxSettings(), {"PYTEST_ADDOPTS": "-x"})
    assert args[:3] == ["docker", "run", "--rm"]
    assert args[args.index("--network") + 1] == "none"
    assert "--cap-drop" in args and "no-new-privileges" in args
    assert f"{tmp_path.resolve()}:/workspace" in args
    assert "PYTEST_ADDOPTS=-x" in args
    assert args[-4:] == ["python", "-m", "pytest", "-q"]


def test_docker_sandbox_fails_closed_without_docker(repo: Path, monkeypatch):
    import agentbridge.validation.runners as runners

    monkeypatch.setattr(runners, "docker_available", lambda _settings=None: False)
    ws = setup_workspace(repo, {"a.txt": "x\n"})
    report = asyncio.run(
        engine(run_lint=False, sandbox="docker").validate(ws.path, ws.base_commit or "")
    )
    tests = report.step("tests")
    assert tests is not None and tests.outcome is Outcome.FAIL
    assert "docker" in tests.summary


def _docker_command() -> list[str] | None:
    if shutil.which("docker"):
        return ["docker"]
    if sys.platform == "win32" and shutil.which("wsl"):
        probe = subprocess.run(["wsl", "-e", "docker", "info"], capture_output=True, check=False)
        if probe.returncode == 0:
            return ["wsl", "docker"]
    return None


DOCKER_COMMAND = _docker_command()


@pytest.mark.skipif(DOCKER_COMMAND is None, reason="docker not available")
def test_docker_sandbox_runs_tests_without_network(repo: Path):
    ws = setup_workspace(
        repo,
        {
            "test_box.py": (
                "import socket, unittest\n\n\nclass T(unittest.TestCase):\n"
                "    def test_no_network(self):\n"
                "        with self.assertRaises(OSError):\n"
                "            socket.create_connection(('1.1.1.1', 53), timeout=3)\n"
            )
        },
    )
    eng = engine(
        run_lint=False,
        sandbox="docker",
        docker={"command": DOCKER_COMMAND},
        test_command=["{python}", "-m", "unittest", "discover", "-v"],
    )
    report = asyncio.run(eng.validate(ws.path, ws.base_commit or ""))
    tests = report.step("tests")
    assert tests is not None and tests.exit_code == 0, tests.output_tail
    assert "Ran 1 test" in tests.output_tail


def test_docker_via_wsl_translates_paths():
    from agentbridge.config.settings import DockerSandboxSettings
    from agentbridge.execution.sandbox import to_wsl_path, wrap_command

    settings = DockerSandboxSettings(command=["wsl", "docker"])
    args = wrap_command(["python", "-V"], Path("E:/work/repo"), settings, {})
    assert args[:3] == ["wsl", "docker", "run"]
    if Path("E:/work/repo").resolve().drive.upper() == "E:":
        assert "/mnt/e/work/repo:/workspace" in args
    assert to_wsl_path(Path("/tmp/x")).endswith("/tmp/x")


def test_docker_command_is_validated():
    from pydantic import ValidationError

    from agentbridge.config.settings import DockerSandboxSettings

    with pytest.raises(ValidationError):
        DockerSandboxSettings(command=["bash", "-c", "rm -rf /"])
