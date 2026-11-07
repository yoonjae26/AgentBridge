# AgentBench

Reproducible evaluation of AI coding agents and agent workflows. Methodology:
[docs/benchmark-methodology.md](../docs/benchmark-methodology.md).

```text
benchmarks/
├── configurations.yaml   which providers/planner each configuration uses
├── suites.yaml           named task lists (core, smoke; "all" is implicit)
├── tasks/<task_id>/
│   ├── task.yaml         task definition (schema: agentbridge.bench.models.BenchmarkTask)
│   ├── repo/             fixture repository
│   ├── hidden_tests/     acceptance tests (copied in after the agent finishes)
│   └── solution/         reference solution (used only by mock-oracle)
├── reports/              curated, real results that are safe to publish
└── experiments/          raw runs (git-ignored)
```

```bash
agentbridge benchmark list
agentbridge benchmark run smoke -c mock-oracle -c mock-noop     # free harness check
agentbridge benchmark run core -c claude-single -n 3            # paid: uses Claude Code
agentbridge benchmark report benchmarks/experiments/<experiment_id>
```

Rules: never edit records by hand, never impute missing values, keep failed and
`not_executable` runs, and publish the configuration and environment metadata with
any result.

## Adding a task

1. Create `tasks/<id>/` with `task.yaml`, `repo/` (include a `pytest.ini`),
   `hidden_tests/test_hidden_*.py` and `solution/`.
2. Check it: `agentbridge benchmark run <id> -c mock-oracle -c mock-noop` must give
   success 1.0 for the oracle and 0.0 for noop.
3. Add it to `suites.yaml`.
