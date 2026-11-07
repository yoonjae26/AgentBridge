# AgentBridge

**One interface. Multiple AI agents. Reliable software delivery.**

AgentBridge is an open-source orchestration framework for AI coding agents. It plans
work, routes tasks to providers that declare the needed capabilities, runs each task
in an isolated git worktree, independently validates the result (lint, type check,
tests, diff review), and never merges anything without your approval.

**AgentBench**, included in this repository, measures agents and agent workflows on
reproducible software-engineering tasks, and reports missing data as missing.

> Status: **v0.1.0 (alpha)**. The CLI workflow, mock provider, Claude Code adapter,
> worktree isolation, validation, Antigravity remote *handoff* and a basic benchmark
> runner work and are tested. See [docs/roadmap.md](docs/roadmap.md) for what is not
> done yet.

## What works today

| Area | Status |
|---|---|
| CLI (`init`, `providers`, `run`, `tasks`, `logs`, `report`, `remote`, `benchmark`) | Working |
| SQLite persistence (WAL), explicit state machine, event history | Working |
| Mock provider (success, failure, delay, interrupt, invalid output, unavailable) | Working |
| Claude Code adapter (`claude -p --output-format json`) | Working, verified with Claude Code 2.1.303 |
| Git worktree per task, diff capture, overlap and merge-conflict detection | Working |
| Validation: diff, scope, isolation, Ruff, Mypy, Pytest, heuristic review | Working |
| Approval-gated merge (`tasks approve`), never force-push, never reset | Working |
| Planner (single / standard template / provider JSON plan), dependency scheduling | Working |
| Retries with exponential backoff, cancellation, restart recovery | Working |
| Google Antigravity | **Manual handoff only** (packet + `remote import`); no automated execution |
| AgentBench (12 tasks, JSON/CSV/Markdown/SVG reports) | Working; no real-agent results published yet |
| Docker isolation, web dashboard, Codex adapter | Not implemented (a generic CLI adapter exists) |

## Quick start

Requirements: Python 3.12+, Git 2.38+. Claude Code is optional (the mock provider
needs no account).

```bash
git clone https://github.com/agentbridge/agentbridge.git
cd agentbridge
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"

# Use AgentBridge in any git repository with at least one commit:
cd /path/to/your/repo
agentbridge init
agentbridge providers list
agentbridge providers check
agentbridge run "Create a Python hello world function" --provider mock
agentbridge tasks list
agentbridge report <task_id>
agentbridge tasks approve <task_id>     # merges into your branch, only when you decide
```

To use Claude Code, install it and log in, confirm `agentbridge providers check`
reports it as available, then run with `--provider claude` (or set
`routing.default_worker: claude` in `agentbridge.yaml`).

## How a task flows

```text
objective -> planner -> task graph -> router -> isolated worktree -> agent
          -> commit agent changes on a task branch -> independent validation
          -> WAITING_FOR_APPROVAL -> (you) tasks approve -> merge into base branch
```

Every state change is recorded. If AgentBridge is killed mid-task, the next command
marks the task `INTERRUPTED`; `agentbridge tasks resume <id>` validates any work
already in the worktree instead of blindly re-running the agent.

## Documentation

- [Installation](docs/installation.md) and [Troubleshooting](docs/troubleshooting.md)
- [Architecture](docs/architecture.md) and [Task lifecycle](docs/task-lifecycle.md)
- [Configuration](docs/configuration.md)
- [Providers](docs/providers.md) and [Provider capability matrix](docs/provider-capabilities.md)
- [Security model](docs/security.md)
- [Benchmark methodology](docs/benchmark-methodology.md) and [benchmarks/README.md](benchmarks/README.md)
- [Roadmap](docs/roadmap.md), [Implementation plan](docs/implementation-plan.md),
  [Development log](docs/development-log.md)
- [Examples](examples/)

## Development

```bash
make check        # ruff + format check + mypy + pytest
make test         # pytest only
make bench-smoke  # AgentBench harness controls on the smoke suite
```

Without make: `ruff check src tests`, `ruff format --check src tests`, `mypy`, `pytest`.

## Important limitations

- A git worktree isolates changes; it is **not** a security sandbox. Agents run with
  your user's permissions. Read [docs/security.md](docs/security.md).
- AgentBridge does not start Antigravity remote agents. It prepares a handoff packet
  and validates the result you import.
- Cost figures from Claude Code are the CLI's own estimate (`total_cost_usd`) and are
  labelled as estimates.

## License

MIT. See [LICENSE](LICENSE). Runtime dependencies (Typer, Rich, Pydantic, SQLAlchemy,
PyYAML) are MIT-licensed.
