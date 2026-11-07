import asyncio
from pathlib import Path

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
