# Roadmap

Dates are intentionally not promised for features that depend on external provider
capabilities.

## v0.1.0 — MVP (this release)

Done: CLI, configuration validation, SQLite persistence and state machine, mock
provider, Claude Code adapter, git worktree isolation, validation pipeline,
approval-gated merge, Antigravity remote handoff, recovery and retries, planner and
dependency scheduling, generic CLI adapter, basic AgentBench (12 tasks) with JSON,
CSV, Markdown and SVG reports, CI workflows.

Not done in v0.1.0 (carried forward):

- Real-agent benchmark results (requires a budgeted run of `claude-single` and
  `claude-multi`, with repetitions).
- Docker isolation for agent processes (validation commands can already run in a
  Docker sandbox).
- Publishing to PyPI and a demo video.

## v0.2.0

- Improved remote workflow (verify any officially documented Antigravity programmatic
  interface; automate only if supported).
- Better scheduling: file-scope-aware parallelism, priority, cost budgets.
- Additional adapters (Codex, OpenCode) once their non-interactive interfaces are
  verified.
- Expanded benchmark tasks from public repositories with clear licenses.

## v0.3.0

- Dashboard: authentication for multi-user setups, run submission from the UI,
  charts over time. (A local single-user dashboard with live monitoring shipped early,
  in the 0.1.x line.)
- Advanced routing (historical success rates, cost/latency estimates).
- Cost optimisation.

## v0.4.0

- Plugin system and custom provider SDK.
- Advanced recovery (provider-side status where supported).
- Distributed workers, only if a demonstrated requirement justifies them.

## v1.0.0

- Stable public API and configuration with migration policy.
- Mature provider ecosystem and reproducible benchmark suite.
- Complete security documentation.
