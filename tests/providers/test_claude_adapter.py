"""Claude Code adapter tested against a fake `claude` executable (no API usage)."""

import asyncio
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from agentbridge.agents.base import ExecutionRequest, ExecutionState
from agentbridge.agents.claude.adapter import ClaudeCodeAdapter
from agentbridge.config.settings import ProviderSettings, RoutingSettings
from tests.conftest import make_settings

FAKE = r"""
import json, os, sys, time
prompt = sys.stdin.read()
log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "w", encoding="utf-8") as fh:
        json.dump({"argv": sys.argv[1:], "prompt": prompt, "cwd": os.getcwd()}, fh)
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
if "--version" in sys.argv:
    print("9.9.9 (Claude Code)")
    sys.exit(0)
if mode == "sleep":
    time.sleep(60)
if mode == "garbage":
    print("this is not json")
    sys.exit(0)
if mode == "crash":
    print("fatal: something broke", file=sys.stderr)
    sys.exit(2)
with open("hello.py", "w", encoding="utf-8") as fh:
    fh.write("def hello():\n    return 'hello world'\n")
result = "Created hello.py"
if mode == "secret":
    result += " using key sk-ant-api03-abcdefghijklmnopqrstuvwxyz"
print(json.dumps({
    "type": "result", "subtype": "success", "is_error": mode == "is_error",
    "result": result, "session_id": "s-1", "num_turns": 2, "duration_ms": 1234,
    "total_cost_usd": 0.0123,
    "usage": {"input_tokens": 10, "cache_creation_input_tokens": 5,
              "cache_read_input_tokens": 100, "output_tokens": 42},
    "modelUsage": {"claude-test-model": {}},
}))
"""


@pytest.fixture
def fake_claude(tmp_path: Path) -> Path:
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE, encoding="utf-8")
    if sys.platform == "win32":
        launcher = tmp_path / "claude.cmd"
        launcher.write_text(f'@"{sys.executable}" "{script}" %*\r\n', encoding="utf-8")
    else:
        launcher = tmp_path / "claude"
        launcher.write_text(
            f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n', encoding="utf-8"
        )
        launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
    return launcher


def request(workdir: Path, out: Path, **kw) -> ExecutionRequest:
    defaults = {
        "task_id": "r1-task-001",
        "execution_id": "r1-task-001-a1",
        "title": "Hello",
        "role": "developer",
        "prompt": "Create hello.py",
        "workdir": workdir,
        "output_dir": out,
        "timeout_seconds": 30,
    }
    return ExecutionRequest(**{**defaults, **kw})


def adapter(fake: Path, **kw) -> ClaudeCodeAdapter:
    return ClaudeCodeAdapter(
        "claude", ProviderSettings(type="claude_code", command=str(fake), **kw)
    )


def test_availability(fake_claude: Path):
    report = asyncio.run(adapter(fake_claude).check_availability())
    assert report.available and report.version == "9.9.9 (Claude Code)"
    missing = asyncio.run(adapter(fake_claude.parent / "nope").check_availability())
    assert not missing.available


def test_successful_execution(fake_claude: Path, tmp_path: Path, monkeypatch):
    log = tmp_path / "log.json"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    work = tmp_path / "work"
    work.mkdir()
    result = asyncio.run(
        adapter(fake_claude, model="some-model").execute(request(work, tmp_path / "out"))
    )
    assert result.state is ExecutionState.COMPLETED
    assert result.summary == "Created hello.py"
    assert (work / "hello.py").exists()
    assert result.usage.input_tokens == 115 and result.usage.output_tokens == 42
    assert result.usage.cost_usd == 0.0123 and result.usage.cost_kind == "estimated"
    assert result.usage.model == "claude-test-model"
    invoked = json.loads(log.read_text(encoding="utf-8"))
    assert invoked["argv"][:5] == [
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        "acceptEdits",
    ]
    assert "--model" in invoked["argv"]
    assert invoked["prompt"] == "Create hello.py"  # prompt via stdin, not argv
    assert Path(invoked["cwd"]).resolve() == work.resolve()
    assert "--dangerously-skip-permissions" not in invoked["argv"]


def test_read_only_uses_plan_mode(fake_claude: Path, tmp_path: Path, monkeypatch):
    log = tmp_path / "log.json"
    monkeypatch.setenv("FAKE_CLAUDE_LOG", str(log))
    asyncio.run(
        adapter(fake_claude).execute(request(tmp_path, tmp_path / "out", agents_may_edit=False))
    )
    argv = json.loads(log.read_text(encoding="utf-8"))["argv"]
    assert argv[argv.index("--permission-mode") + 1] == "plan"


@pytest.mark.parametrize(
    ("mode", "state", "retryable"),
    [
        ("garbage", ExecutionState.INVALID_OUTPUT, False),
        ("crash", ExecutionState.FAILED, True),
        ("is_error", ExecutionState.FAILED, True),
    ],
)
def test_failure_modes(fake_claude, tmp_path, monkeypatch, mode, state, retryable):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", mode)
    result = asyncio.run(adapter(fake_claude).execute(request(tmp_path, tmp_path / "out")))
    assert result.state is state
    assert result.retryable is retryable


def test_timeout_kills_process(fake_claude, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep")
    result = asyncio.run(
        adapter(fake_claude).execute(request(tmp_path, tmp_path / "out", timeout_seconds=2))
    )
    assert result.state is ExecutionState.TIMED_OUT
    assert result.retryable
    assert result.duration_seconds is not None and result.duration_seconds < 30


def test_cancellation(fake_claude, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "sleep")
    claude = adapter(fake_claude)

    async def go():
        task = asyncio.create_task(claude.execute(request(tmp_path, tmp_path / "out")))
        await asyncio.sleep(1.0)
        assert await claude.cancel("r1-task-001-a1")
        return await asyncio.wait_for(task, timeout=20)

    assert asyncio.run(go()).state is ExecutionState.CANCELLED


def test_secrets_redacted_from_output(fake_claude, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_CLAUDE_MODE", "secret")
    result = asyncio.run(adapter(fake_claude).execute(request(tmp_path, tmp_path / "out")))
    assert "sk-ant" not in result.summary
    assert "sk-ant" not in Path(result.output_path or "").read_text(encoding="utf-8")


def test_claude_through_orchestrator(fake_claude, orchestrator_factory, monkeypatch):
    monkeypatch.delenv("FAKE_CLAUDE_MODE", raising=False)
    settings = make_settings(
        providers={"claude": ProviderSettings(type="claude_code", command=str(fake_claude))},
        routing=RoutingSettings(planner="claude", default_worker="claude"),
    )
    orchestrator = orchestrator_factory(settings)

    async def go():
        run_id = await orchestrator.submit("Create a hello world function")
        return await orchestrator.execute_run(run_id)

    summary = asyncio.run(go())
    task = orchestrator.store.get_task(summary.task_ids[0])
    assert task.status == "WAITING_FOR_APPROVAL", task.error_message
    assert task.assigned_provider == "claude"
    assert task.changed_files == ["hello.py"]
    execution = orchestrator.store.list_executions(task.id)[0]
    assert execution.cost_usd == 0.0123
    assert execution.cost_source == "estimated:claude_cli:total_cost_usd"
    assert execution.output_tokens == 42
    assert os.path.exists(execution.output_path or "")
