# Changelog

All notable changes are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## Unreleased

### Added

- Local web dashboard: `agentbridge dashboard` (FastAPI backend, React + TypeScript
  frontend shipped prebuilt). Overview, runs, task graph, task detail with diff,
  validation steps, agent output and event timeline, live updates over server-sent
  events, token-protected approve/reject/cancel, AgentBench results. Loopback only.

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
