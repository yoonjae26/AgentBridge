"""Container isolation for Claude Code: no credentials or personal data leak."""

import asyncio
from pathlib import Path

from agentbridge.agents.base import ExecutionRequest, ExecutionState
from agentbridge.agents.claude.adapter import ClaudeCodeAdapter
from agentbridge.agents.claude.container import container_environment, docker_run_args
from agentbridge.config.settings import AgentContainerSettings, ProviderSettings

TOKEN = "sk-ant-oat01-SECRETSECRETSECRETSECRET"


def settings(**kw) -> AgentContainerSettings:
    return AgentContainerSettings(enabled=True, **kw)


def test_token_passed_by_name_only_and_nothing_personal_mounted(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    args = docker_run_args(settings(), tmp_path, "r1-task-001-a1", ["claude", "-p"])
    joined = " ".join(args)
    assert TOKEN not in joined
    token_pos = args.index("CLAUDE_CODE_OAUTH_TOKEN")
    assert args[token_pos - 1] == "-e"  # passed by name; docker reads the value
    mounts = [args[i + 1] for i, a in enumerate(args) if a == "-v"]
    assert mounts == [f"{tmp_path.resolve()}:/workspace"]
    # Only the worktree is mounted; nothing else from the home directory, never ~/.claude.
    assert not any(".claude" in m for m in mounts)
    assert all(str(Path.home() / d) not in joined for d in (".claude", ".ssh", ".aws"))
    for flag in ("--read-only", "--rm", "no-new-privileges"):
        assert flag in args
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert args[-4:] == ["--disallowedTools", "Bash", "WebFetch", "WebSearch"]


def test_container_environment_is_minimal(monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_should_not_leak_000000000000000000")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "should-not-leak")
    env = container_environment(settings())
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == TOKEN
    assert "GITHUB_TOKEN" not in env and "AWS_SECRET_ACCESS_KEY" not in env
    wsl_env = container_environment(settings(command=["wsl", "docker"]))
    assert wsl_env["WSLENV"] == "CLAUDE_CODE_OAUTH_TOKEN/u"


def test_fails_closed_without_token(tmp_path: Path, monkeypatch):
    import agentbridge.agents.claude.adapter as module

    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    monkeypatch.setattr(module, "resolve_executable", lambda name: f"/usr/bin/{name}")
    adapter = ClaudeCodeAdapter(
        "claude", ProviderSettings(type="claude_code", container=settings())
    )
    report = asyncio.run(adapter.check_availability())
    assert not report.available and report.auth == "missing"
    request = ExecutionRequest(
        task_id="t",
        execution_id="t-a1",
        title="x",
        role="developer",
        prompt="p",
        workdir=tmp_path,
        output_dir=tmp_path / "out",
        timeout_seconds=30,
    )
    result = asyncio.run(adapter.execute(request))
    assert result.state is ExecutionState.UNAVAILABLE
