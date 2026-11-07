# AgentBench methodology

**Research question.** Does multi-agent collaboration improve software-engineering
task completion compared with individual AI coding agents, and under which conditions
does it provide measurable benefits?

AgentBench is designed so that it can show a single agent performing better. It
produces reproducible records, not marketing claims.

## Dataset

Twelve curated, deterministic tasks (`benchmarks/tasks/<task_id>/`), authored for
AgentBench and released under MIT, covering all eight categories:

| Category | Tasks |
|---|---|
| Bug fixing | bugfix-001 (slugify), bugfix-002 (median), bugfix-003 (pagination) |
| Feature implementation | feature-001 (email validator), feature-002 (LRU cache), feature-003 (duration parser) |
| Refactoring | refactor-001 (remove deprecated API, behaviour unchanged) |
| Unit-test generation | tests-001 (tests must kill four mutants) |
| Documentation | docs-001 (docstrings + README usage) |
| Code review | review-001 (find SQL injection and unsafe password comparison) |
| Dependency update | deps-001 (bump a vulnerable pin, keep others) |
| Repository analysis | analysis-001 (modules, entry point, untested modules) |

Each task directory contains:

- `task.yaml` — `task_id`, `repository`, `base_commit`, `issue_description`,
  `task_category`, `acceptance_criteria`, `setup_commands`, `test_commands`,
  `regression_test_command`, `timeout`, `difficulty`, `expected_files`, `license`.
- `repo/` — the fixture repository (includes `pytest.ini` so pytest never picks up
  configuration from parent directories).
- `hidden_tests/` — acceptance tests, copied into the result workspace **only after
  the agent has finished**, so agents cannot see or edit them.
- `solution/` — a reference solution used only by the `mock-oracle` control.

The dataset uses small synthetic repositories rather than public projects. This makes
runs fast, offline and license-clean, at the cost of realism. Tasks from real public
repositories and issues are planned (see roadmap); their licenses must be checked
before redistribution.

**Base commits.** Fixture tasks have `base_commit: null` in `task.yaml` because the
repository is synthesised at run time: files are copied with LF line endings and
committed with a fixed author, committer and date (2025-01-01T00:00:00Z), so the same
fixture always yields the same commit hash. Each record stores the actual
`base_commit` and a SHA-256 `fixture_digest` of the fixture content.

**Keyword-based checks.** Code review, analysis and documentation tasks are judged by
deterministic checks (e.g. REVIEW.md must name the function and mention injection).
These are proxies for quality and can be gamed; treat those categories with care.

## Configurations

| Name | Kind | What runs |
|---|---|---|
| `mock-oracle` | control | Mock writes the reference solution. Expected: 100% success. Validates the harness. |
| `mock-noop` | control | Mock writes an unrelated file. Expected: 0% success. Shows tests cannot pass without a change. |
| `claude-single` | A: single agent | One Claude Code developer task. |
| `antigravity-remote` | B: single remote agent | Manual handoff → recorded as `not_executable`. |
| `claude-antigravity` | C: two-agent | Claude planner + Antigravity worker → `not_executable` (manual handoff). |
| `claude-multi` | D: multi-agent (single vendor) | Claude analyst → Claude developer → Claude reviewer, plus an agent review of the diff. |

Configurations that cannot run without a human or with an unavailable provider are
recorded as `not_executable` with the reason; they are excluded from rates and never
counted as failures or successes. Note that `claude-multi` uses the same model in
every role, so it measures *workflow structure*, not cross-vendor collaboration.

## Procedure per (task, configuration, repetition)

1. Materialise the fixture as a fresh git repository (deterministic base commit).
2. Run `setup_commands` (policy-checked) and record per-test baseline results of
   `regression_test_command`.
3. Submit the issue text plus acceptance criteria to the AgentBridge orchestrator with
   the configuration's providers and planner mode. Validation runs as usual (tests on;
   lint and type check off for speed).
4. Copy `hidden_tests/` into the final task workspace and run `test_commands`.
5. Re-run the regression tests; any test that passed at baseline and does not pass now
   is a regression.
6. Dry-run a merge of the result branch into the base (`git merge-tree`).
7. Write `records/<task>__<config>__<rep>.json`.

All configurations receive the identical issue text, acceptance criteria, timeout
(`task.timeout`) and starting commit.

## Metrics

| Metric | Definition | Missing data |
|---|---|---|
| Task success rate | Runs where all hidden tests passed / executed runs (`error` counts as unsuccessful) | `null` if no executed runs |
| Test pass rate | Hidden tests passed / hidden tests run | `null` if none ran |
| Execution time | Wall clock from submit to end of AgentBridge run (excludes hidden tests) | `null` |
| Measured cost | Billing data. **Not collected** in v0.1.0 | always `null` |
| Estimated cost | Sum of provider-reported estimates, with `estimated_cost_source` | `null` if no provider reported |
| Token usage | Sum of provider-reported tokens | `null` if not reported |
| Regression rate | Runs with ≥1 regressed baseline test / runs with a regression command | `null` |
| Retry rate | Mean retries per executed run | `null` |
| Failure rate | Runs with status `failed` or `error` / executed runs | `null` |
| Human interventions | Count of manual steps (remote handoff = 1) | `null` |
| Merge success rate | Runs whose branch merges cleanly into base / runs with a branch | `null` |

Unknown values are `null` (shown as `n/a`), never zero.

## Fairness rules

- Same repository state, task text, acceptance criteria and time limit for all
  configurations.
- Provider/model versions are recorded per run (`providers` field and execution
  records); environment metadata is in `metadata.json`.
- Failures and `not_executable` runs are kept in the records.
- Repeat stochastic runs with `--repetitions N` when budget allows; report variance.
- Quality, speed and cost are reported separately; there is no combined score.

## Outputs

`benchmarks/experiments/<experiment_id>/`: `metadata.json`, `records/*.json`,
`records.csv`, `summary.csv`, `summary.json`, `report.md`, `success_rate.svg`,
`execution_time.svg`, and `work/` (all workspaces, for inspection).
`agentbridge benchmark report <dir>` regenerates every derived file from `records/`.

## Results

Only harness-control results have been produced so far (see
`benchmarks/reports/`). **No real-agent comparison has been run or published.** Do
not cite any multi-agent vs single-agent conclusion from this repository until such
results exist.
