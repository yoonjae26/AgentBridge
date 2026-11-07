# Harness control run (real data)

Produced by `agentbridge benchmark run core -c mock-oracle -c mock-noop -c antigravity-remote`
on 2026-11-07 (UTC), Windows 11, Python 3.12.7, Git 2.53.0. Copied from
`benchmarks/experiments/exp-20261107-150522-30d0/` without the `work/` directory.

What it shows:

- `mock-oracle` (reference solutions) passes 12/12 tasks: fixtures and hidden tests
  are consistent.
- `mock-noop` (no real change) passes 0/12: hidden tests cannot be passed without
  doing the task.
- `antigravity-remote` is `not_executable` (manual handoff) and is excluded from rates.

What it does **not** show: anything about the quality of AI agents. No real-agent
benchmark has been run yet.
