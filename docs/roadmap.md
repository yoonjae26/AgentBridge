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
- Alembic migrations (schema is versioned but created from metadata).
- Docker isolation for agent processes.
- Publishing to PyPI and a demo video.

## v0.2.0

- Improved remote workflow (verify any officially documented Antigravity programmatic
  interface; automate only if supported).
- Better scheduling: file-scope-aware parallelism, priority, cost budgets.
- Additional adapters (Codex, OpenCode) once their non-interactive interfaces are
  verified.
- Expanded benchmark tasks from public repositories with clear licenses.
- Alembic migrations.

## v0.3.0

- Web dashboard and live execution monitoring (FastAPI + React), only after the CLI
  workflow is proven reliable.
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
