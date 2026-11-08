# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## Unreleased

### Changed

- Split into two distributions: **`agentbridge-core`** (the `agentbridge` command;
  import name unchanged) and **`agentbridge-bench`** (AgentBench, import
  `agentbridge_bench`, command `agentbridge-bench`). The PyPI name `agentbridge` belongs
  to an unrelated project. `agentbridge benchmark …` still works when
  `agentbridge-bench` is installed and prints an install hint otherwise.
- The `agentbridge-bench` wheel bundles the benchmark suite and works outside a source
  checkout.

### Fixed

- AgentBench refuses to run without pytest, and a test command that fails without a
  pytest summary now counts as a failure instead of silently reporting 0/0.

### Added

- Local web dashboard: `agentbridge dashboard` (FastAPI backend, React + TypeScript
  frontend shipped prebuilt). Overview, runs, task graph, task detail with diff,
  validation steps, agent output and event timeline, live updates over server-sent
  events, token-protected approve/reject/cancel, AgentBench results. Loopback only.
- Alembic schema migrations; pre-Alembic databases are upgraded in place.
- `validation.sandbox: docker`: validation commands run in a network-less,
  resource-limited container and fail closed if Docker is unavailable.
  `validation.docker.command: [wsl, docker]` supports Docker inside WSL on Windows.

- Claude Code container isolation (`providers.claude.container`): only the worktree
  is mounted, a single token is passed by variable name, read-only root filesystem,
  dropped capabilities, shell/web tools disallowed, fail-closed.

### Fixed

- Execution records no longer stay `running` when an adapter raises.
- Third-party test-client deprecation warning silenced.

## 0.1.0 - 2026-11-08

### Added

- `agentbridge` CLI: `init`, `providers list|check`, `run`, `tasks
  list|status|inspect|resume|cancel|approve|reject|cleanup`, `logs`, `report`,
  `remote packet|import`, `benchmark list|run|report`, with stable exit codes.
- Validated `agentbridge.yaml` configuration with safe defaults.
- SQLite persistence (WAL), explicit task state machine with atomic transitions and
  event history, restart recovery and safe resume.
- Adapter contract with declared capabilities; mock, Claude Code CLI, Antigravity
  remote handoff and generic CLI adapters.
- Planner (single, standard template, provider JSON plan), explainable router,
  dependency-aware scheduler, retries with exponential backoff, cancellation.
- Git worktree isolation, diff capture, overlap and merge-conflict detection,
  approval-gated merge.
- Validation pipeline: diff, scope, isolation, Ruff, Mypy, Pytest, heuristic review,
  optional agent review.
- Security: policy profiles, command allowlists, protected git operations, secret
  redaction, path traversal protection.
- Task and run reports (JSON + Markdown).
- AgentBench: 12 deterministic tasks across 8 categories, controls, runner, metrics,
  JSON/CSV/Markdown/SVG reports.
