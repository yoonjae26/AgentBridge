# Architecture

AgentBridge is a modular monolith written in Python 3.12. There is no server, queue
or external database: one CLI process orchestrates work and persists state in SQLite.

```text
                         DEVELOPER
                             |
                     agentbridge CLI (Typer + Rich)           cli/
                             |
                        ORCHESTRATOR                           core/orchestrator.py
            +----------------+-----------------+
            |                |                 |
         PLANNER           ROUTER         SCHEDULER (in orchestrator)
     core/planner.py   core/router.py    dependency-aware, max_parallel_tasks
            +----------------+-----------------+
                             |
                       AGENT ADAPTERS                          agents/
          mock | claude_code | antigravity_remote | generic_cli
                             |
             +---------------+----------------+
             |               |                |
        WORKSPACES       TASK STATE       EVENT LOG
       workspace/      storage/ + tasks/   core/events.py
       (git worktrees)  (SQLite, WAL)      (DB + .agentbridge/logs)
                             |
                      VALIDATION ENGINE                        validation/
        diff -> scope -> isolation -> lint -> type check -> tests -> review
                             |
            WAITING_FOR_APPROVAL  --(human: tasks approve)-->  INTEGRATION
                             |                              workspace/integration.py
                       REPORTS (JSON + Markdown)               reporting/
                             |
                         AGENTBENCH                            agentbridge_bench + benchmarks/
```

## Modules

| Package | Responsibility |
|---|---|
| `cli/` | Commands, output formatting, error-to-exit-code mapping (`errors.ExitCode`). |
| `config/` | Pydantic models for `agentbridge.yaml`; loading, validation, defaults. |
| `core/orchestrator.py` | Submit (plan + persist), schedule, execute attempts with retry/backoff, heartbeat and cancellation, validation, approve/reject, resume, remote import. |
| `core/planner.py` | `single` and `standard` template plans; `provider` mode asks a provider for JSON and validates it with Pydantic. |
| `core/router.py` | Chooses a provider from explicit request, `routing.roles`, role defaults and `default_worker`, checking enablement, declared capabilities, availability and policy. Every decision carries an explanation. |
| `agents/` | `AgentAdapter` contract (`base.py`), capability model, registry and adapters. |
| `tasks/` | Task/plan schemas, explicit state machine, dependency graph validation, startup recovery. |
| `storage/` | SQLAlchemy 2.x models and the `Store` data-access layer (atomic compare-and-swap transitions). |
| `workspace/` | Git wrapper that refuses protected operations, worktree manager, diffs, overlap/merge-conflict detection, approval-gated merge. |
| `validation/` | Command runners (policy-checked), deterministic diff review, aggregation into PASS/FAIL/WARNING/NEEDS_HUMAN_REVIEW. |
| `security/` | Policy profiles, command permission checks, secret redaction, path validation. |
| `reporting/` | Task and run reports. |
| `agentbridge_bench` (package `agentbridge-bench`) | AgentBench schemas, dataset loading, runner, metrics, reports and the `agentbridge-bench` CLI. Depends on `agentbridge-core`; the core never requires it. |

## Key design decisions

1. **State machine first.** Every status change goes through `Store.transition`, which
   validates the transition, performs a compare-and-swap `UPDATE ... WHERE status = ?`
   and writes an event in the same transaction.
2. **Agents are untrusted.** Agent output is never executed. AgentBridge commits what
   the agent changed on a task branch and validates it with its own commands.
3. **Approval is structural.** `INTEGRATING` is reachable only from
   `WAITING_FOR_APPROVAL`, and the config validator rejects disabling approval.
4. **Capabilities are declared, not assumed.** The router never sends a task to a
   provider that has not declared every required capability. The Antigravity adapter
   declares `human_in_the_loop` and no `local_workspace`.
5. **Downstream tasks build on validated upstream branches.** A task whose dependency
   is awaiting merge approval starts from that dependency's branch, so a multi-step
   plan does not need an approval between each step. Approving the last task merges
   the chain.
6. **No hidden infrastructure.** SQLite (WAL) is sufficient for one developer machine.
   The schema is managed by Alembic (`storage/migrations`) and upgraded automatically
   when a database is opened; databases from before Alembic are stamped at `0001`.

## Data layout in a project

```text
your-repo/
├── agentbridge.yaml            configuration (no credentials)
└── .agentbridge/               excluded via .git/info/exclude
    ├── agentbridge.db          SQLite (runs, tasks, events, executions, validations)
    ├── worktrees/<task_id>/    one git worktree per local task
    ├── logs/<task_id>.log      human-readable event log
    ├── artifacts/<task_id>/    raw agent output, remote handoff packets
    ├── cache/                  validation tool caches (kept out of worktrees)
    └── reports/                <task_id>.{json,md}, <run_id>.{json,md}
```
