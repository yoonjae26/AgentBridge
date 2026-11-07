import asyncio

import pytest

from agentbridge.config.settings import PolicyProfile, ProviderSettings
from agentbridge.errors import PolicyViolationError
from agentbridge.security.paths import resolve_inside, validate_relative_path
from agentbridge.security.permissions import check_command, is_protected_git_operation
from agentbridge.security.policies import build_policy
from agentbridge.security.secrets import REDACTED, contains_secret, redact
from agentbridge.validation.review import review_diff
from agentbridge.workspace.diff import DiffSummary, FileChange
from agentbridge.workspace.git import Git
from tests.conftest import make_settings

STANDARD = build_policy(PolicyProfile.STANDARD)


# ------------------------------------------------------------ secret redaction
@pytest.mark.parametrize(
    "secret",
    [
        "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123",
        "sk-proj-abcdefghijklmnopqrstuvwxyz012345",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "AKIAABCDEFGHIJKLMNOP",
        "xoxb-1234567890-abcdefghij",
    ],
)
def test_known_token_formats_redacted(secret):
    text = f"error while using {secret} in request"
    assert secret not in redact(text)
    assert REDACTED in redact(text)
    assert contains_secret(text)


def test_assignment_and_bearer_redacted():
    out = redact('API_KEY="supersecretvalue123" and Authorization: Bearer abcdefghijklmnop12345')
    assert "supersecretvalue123" not in out
    assert "abcdefghijklmnop12345" not in out


def test_environment_secret_values_redacted(monkeypatch):
    monkeypatch.setenv("MY_SERVICE_TOKEN", "plain-looking-value-42")
    assert "plain-looking-value-42" not in redact("value: plain-looking-value-42")


def test_ordinary_text_untouched():
    text = "Ran 12 tests in 0.3s; token_usage is unavailable"
    assert redact(text, use_env=False) == text


# ----------------------------------------------------------- command policies
@pytest.mark.parametrize(
    "args",
    [
        ["rm", "-rf", "/"],
        ["bash", "-c", "echo hi"],
        ["powershell", "-Command", "Remove-Item"],
        ["curl", "http://evil.example"],
        ["python", "-c", "import os; os.remove('x')"],
        ["python", "-m", "http.server"],
        ["pytest", "tests; rm -rf ~"],
        ["pytest", "$(whoami)"],
        ["git", "push", "--force", "origin", "main"],
        ["git", "push", "origin", "+main"],
        ["git", "reset", "--hard", "HEAD~1"],
        ["git", "clean", "-fdx"],
        ["git", "-C", "/repo", "branch", "-D", "main"],
        ["node_modules/.bin/evil"],
        [],
    ],
)
def test_unsafe_commands_rejected(args):
    with pytest.raises(PolicyViolationError):
        check_command(args, STANDARD)


@pytest.mark.parametrize(
    "args",
    [
        ["python", "-m", "pytest", "-q"],
        ["C:\\Python312\\python.exe", "-m", "ruff", "check", "."],
        ["mypy", "."],
        ["git", "status"],
    ],
)
def test_safe_commands_allowed(args):
    check_command(args, STANDARD)


def test_safe_profile_is_stricter():
    safe = build_policy(PolicyProfile.SAFE)
    assert not safe.agents_may_edit
    assert safe.claude_permission_mode == "plan"
    with pytest.raises(PolicyViolationError):
        check_command(["npm", "test"], safe)
    check_command(["npm", "test"], STANDARD)


def test_trusted_still_blocks_protected_operations():
    trusted = build_policy(PolicyProfile.TRUSTED, ["deploy-tool"])
    check_command(["deploy-tool", "--dry-run"], trusted)
    with pytest.raises(PolicyViolationError):
        check_command(["git", "push", "--force"], trusted)


def test_git_wrapper_refuses_protected_operations(repo):
    with pytest.raises(PolicyViolationError):
        Git(repo).run("reset", "--hard", "HEAD")
    assert is_protected_git_operation(["git", "push", "--force-with-lease"])
    assert not is_protected_git_operation(["git", "push", "origin", "feature"])


# --------------------------------------------------------- path traversal
@pytest.mark.parametrize(
    "raw",
    [
        "../outside.txt",
        "a/../../b",
        "/etc/passwd",
        "C:\\Windows\\x",
        "C:/x",
        ".git/config",
        "src/.ssh/id_rsa",
        "",
        ".",
    ],
)
def test_path_traversal_rejected(raw):
    with pytest.raises(PolicyViolationError):
        validate_relative_path(raw)


def test_resolve_inside(tmp_path):
    assert resolve_inside(tmp_path, "a/b.txt") == (tmp_path / "a" / "b.txt").resolve()
    with pytest.raises(PolicyViolationError):
        resolve_inside(tmp_path, "../x")


# ------------------------------------------------- untrusted agent behaviour
def test_agent_cannot_write_outside_workspace(orchestrator_factory, repo):
    settings = make_settings(providers={"mock": ProviderSettings(type="mock")})
    orchestrator = orchestrator_factory(settings)

    async def go():
        run_id = await orchestrator.submit(
            "Write files", metadata={"mock_files": {"../../escaped.txt": "pwned"}}
        )
        return await orchestrator.execute_run(run_id)

    summary = asyncio.run(go())
    task = orchestrator.store.get_task(summary.task_ids[0])
    assert task.status == "FAILED"
    assert "traversal" in (task.error_message or "").lower()
    assert not (repo.parent / "escaped.txt").exists()
    assert not (repo / "escaped.txt").exists()


def test_review_flags_dangerous_changes():
    patch = "\n".join(
        [
            "+++ b/app.py",
            "+result = eval(user_input)",
            "+subprocess.run(cmd, shell=True)",
            "+++ b/tests/test_app.py",
            "+@pytest.mark.skip",
        ]
    )
    diff = DiffSummary(
        base="a",
        head="b",
        files=[
            FileChange(path="app.py", status="M"),
            FileChange(path=".github/workflows/ci.yml", status="M"),
            FileChange(path="tests/test_old.py", status="D"),
        ],
        patch=patch,
    )
    messages = {f.message for f in review_diff(diff)}
    assert {
        "Use of eval/exec",
        "subprocess with shell=True",
        "Test skipped or marked xfail",
        "Sensitive file modified",
        "Test file deleted",
    } <= messages


def test_review_blocks_committed_credentials():
    diff = DiffSummary(
        base="a",
        head="b",
        files=[FileChange(path="config.py", status="M")],
        patch="+++ b/config.py\n+KEY = 'sk-ant-api03-abcdefghijklmnopqrstuvwx'\n",
    )
    assert any(f.severity == "critical" for f in review_diff(diff))


def test_malicious_task_input_is_not_executed(orchestrator_factory, repo):
    """Shell syntax in an objective is just text in a prompt; nothing runs it."""
    orchestrator = orchestrator_factory()
    marker = repo / "PWNED"

    async def go():
        run_id = await orchestrator.submit(f"Fix bug; touch {marker} && rm -rf . `id`")
        return await orchestrator.execute_run(run_id)

    asyncio.run(go())
    assert not marker.exists()
    assert (repo / "README.md").exists()
