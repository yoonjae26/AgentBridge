# Implementation plan (v0.1.0)

## 1. Environment inspection (2026-11-07)

| Item | Result |
|---|---|
| Working directory | Empty; project created at `E:\agentbridge` (system drive C: low on space, so the venv, uv cache and test temp dirs are also on E:) |
| Existing repository | None; new git repository initialised on `main` |
| OS | Windows 11 Pro (10.0.26300) |
| Python | 3.12.7 (Anaconda) |
| Git | 2.53.0.windows.2 |
| uv | 0.10.9 |
| Claude Code CLI | 2.1.303, on PATH; `-p`, `--output-format json`, `--permission-mode` confirmed via `--help` |
| Antigravity CLI (`agy`) | Not installed |
| Codex CLI | Not installed |

## 2. Architecture decisions

- Modular monolith; Typer + Rich CLI; Pydantic v2 models; SQLAlchemy 2.x on SQLite
  (WAL); asyncio for concurrent tasks and subprocesses; git via subprocess.
- Explicit state machine with compare-and-swap transitions and an event per change.
- Typed adapter contract with declared capabilities; unsupported operations explicit.
- Worktree per task; agent changes committed by AgentBridge on a task branch;
  downstream tasks branch from upstream task branches.
- Validation independent of agent claims; aggregation into PASS / FAIL / WARNING /
  NEEDS_HUMAN_REVIEW.
- Merge only via explicit approval; protected git operations refused in code.
- Antigravity as human-in-the-loop handoff (no verified headless API).
- AgentBench uses offline synthetic fixtures with hidden tests, controls
  (oracle/noop), and records `null` for anything unmeasured.

## 3. Modules (in implementation order)

1. Project foundation (`pyproject.toml`, package layout, errors/exit codes)
2. CLI (`cli/`)
3. Configuration (`config/`)
4. Database (`storage/`)
5. Task state machine (`tasks/`)
6. Mock adapter (`agents/mock`)
7. Unit tests
8. Claude Code adapter (`agents/claude`)
9. Git worktree manager (`workspace/`)
10. Validation engine (`validation/`)
11. Antigravity remote handoff (`agents/antigravity`, `remote` commands)
12. Orchestrator, planner, router, recovery (`core/`, `tasks/recovery.py`)
13. AgentBench (`bench/`, `benchmarks/`)
14. Documentation (`docs/`, README, community files)
15. CI/CD (`.github/workflows`)

## 4. Dependencies

Runtime: typer, rich, pydantic, SQLAlchemy, PyYAML (all MIT).
Development: pytest, pytest-cov, ruff, mypy, types-PyYAML.
Version ranges are bounded in `pyproject.toml`.

## 5. Testing strategy

- Unit: state machine, dependencies, planner parsing, config validation, store,
  routing, retry/backoff, branch naming, metrics.
- Integration: worktree lifecycle, validation pipeline, orchestration with the mock
  provider (scheduling, recovery, cancel, approve/reject), CLI end-to-end including
  the specification's email-validator scenario.
- Providers: Claude adapter against a fake `claude` executable (success, invalid
  output, crash, error result, timeout, cancellation, redaction, argv/stdin contract);
  Antigravity handoff with a bare git repository acting as the remote.
- Security: redaction, command policies, protected git operations, path traversal,
  untrusted agent output, malicious objectives.
- Benchmarks: dataset completeness, deterministic fixtures, controls, reproducible
  reports.
- Gates: `ruff check`, `ruff format --check`, `mypy --strict`, `pytest`.

## 6. Known risks

| Risk | Mitigation |
|---|---|
| Provider CLIs change flags/output | Version recorded; parsing tolerant; tests use a fake CLI; capability matrix dated. |
| Agents escape the worktree | Isolation check on the primary checkout; documented that worktrees are not sandboxes. |
| Benchmark tasks too easy / synthetic | Controls validate the harness; real-repository tasks on the roadmap. |
| Keyword-based checks for review/analysis tasks | Documented as proxies. |
| Windows process-tree termination | `taskkill /T /F`; covered by timeout/cancel tests on Windows. |

## 7. Completion criteria

The specification's Definition of Done (§29–§32). Status per item is tracked in
[development-log.md](development-log.md).
