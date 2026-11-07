# Development log

All results below were produced by commands actually run in the development
environment (Windows 11, Python 3.12.7, Git 2.53.0, Claude Code 2.1.303). Nothing
here is projected or estimated.

## 2026-11-07/08 — v0.1.0 implementation session

### Milestone 1: foundation, CLI, config, storage, state machine, mock

- Implemented: package layout, exit-code contract, Typer CLI, validated YAML config,
  SQLite (WAL) store with compare-and-swap transitions and events, state machine,
  mock adapter (six scenarios).
- Verified by hand in a sandbox repository: `agentbridge init`, `providers list`,
  `providers check` (claude available, auth credentials present; antigravity
  disabled; mock available), `run "Create a Python hello world function" --provider
  mock` → `WAITING_FOR_APPROVAL`, `tasks list`, `report <task_id>`,
  `tasks approve` → merge commit on `main`, second approve rejected with exit code 7.

### Milestone 2: Claude Code adapter

- Implemented `claude -p --output-format json --permission-mode <mode>` with the
  prompt on stdin, timeout and process-tree cancellation, usage/cost parsing (cost
  labelled as the CLI's estimate), redaction of stored output.
- Real smoke run (one task: `hello.py` + one test): completed in ~20 s; Claude edited
  three files (it also added `pythonpath = .` to `pytest.ini`); it could not run
  shell commands under `acceptEdits`, as intended; AgentBridge validation: lint PASS,
  type check PASS, tests 1 passed, review PASS; primary checkout unchanged. Reported
  usage: 230,038 input tokens (incl. cache) / 1,484 output; CLI-estimated cost
  USD 0.19. This is a single smoke check, not a benchmark.

### Milestone 3: worktrees, validation, approval

- Implemented worktree manager, diff capture, overlap and `git merge-tree` conflict
  detection, approval-gated merge, validation pipeline and heuristic review.
- Bug found and fixed: AgentBridge set `core.autocrlf=false` after creating a
  worktree, which wrote to the user's shared repository config and, on machines with
  `autocrlf=true`, produced spurious line-ending "changes". The setting was removed
  and a regression test added.
- Bug found and fixed: pytest/ruff caches created during validation looked like
  uncommitted changes and blocked approval. Validation now runs with
  `PYTHONDONTWRITEBYTECODE`, `-p no:cacheprovider`, `RUFF_NO_CACHE` and a mypy cache
  outside the worktree; agent commits exclude tool cache directories via pathspecs.
- Bug found and fixed: a failed dependency only failed its direct dependents in one
  scheduling pass; propagation now repeats until stable.

### Milestone 4: Antigravity remote handoff

- Implemented packet generation (JSON + Markdown, credentials stripped from remote
  URLs, warnings for missing remote / unpushed base), `remote packet`, `remote import`
  (fetch, ancestry check, new worktree, validation), approval.
- Tested end to end with a bare git repository acting as the hosted remote. The `agy`
  CLI was not installed, so no real Antigravity session was run.

### Milestone 5: orchestration

- Planner (single / standard / provider JSON), router with explanations, dependency
  scheduling with `max_parallel_tasks`, retries with exponential backoff, heartbeat,
  cancellation, startup recovery, safe resume, optional agent review.

### Milestone 6: AgentBench

- 12 tasks across all 8 categories, configurations (controls, Claude single, Claude
  multi-role, Antigravity configurations), runner, metrics, JSON/CSV/Markdown/SVG.
- Harness control run (`benchmarks/reports/harness-controls-exp-20261107-150522/`):
  `mock-oracle` 12/12 success, `mock-noop` 0/12 (hidden-test pass rate 0.27 from
  tests that check unchanged behaviour), `antigravity-remote` 12 × `not_executable`.
  Mean AgentBridge time per run ≈ 1.0 s. Costs and tokens `n/a`.
- Bug found and fixed: the database was opened before its directory existed in
  benchmark workspaces; the fixture digest included `.git`.
- **Not run:** `claude-single` and `claude-multi` on the suite (paid; needs an
  explicit budget decision).

### Milestone 7–8: docs, CI, release checks

- Documentation set, examples (simple_task verified by hand: 2 files changed, lint/
  type/tests PASS, approve merged), community files, issue/PR templates, CI workflows.
- Wheel and sdist built with `uv build`; wheel installed into a clean virtual
  environment; `agentbridge --version`, `init` and a mock `run` succeeded.
- CI workflows were written but have **not** been executed on GitHub (no remote
  repository exists yet).

### Final gate (last run)

| Check | Result |
|---|---|
| `ruff check src tests` | All checks passed |
| `ruff format --check src tests` | 90 files already formatted |
| `mypy` (strict, 68 source files) | No issues |
| `pytest` | **160 passed** (unit 63, integration 29, security 44, providers 14, benchmarks 10) in ~67 s |
| Coverage | 88% of `agentbridge` |

### Known limitations

- Worktrees are not sandboxes; Docker isolation not implemented.
- Execution status cannot be recovered from Claude Code after a restart; such tasks
  become `INTERRUPTED` and resume conservatively.
- Alembic migrations not implemented (schema version stored in `meta`).
- Benchmarks need a source checkout (the `benchmarks/` data is not in the wheel) or
  `--benchmarks-dir`.
- Review/analysis/docs benchmark checks are keyword-based proxies.
- The mock "review" always passes; it is not a real review.

### Remaining work

See [roadmap.md](roadmap.md): real-agent benchmark runs with repetitions, Alembic,
Docker isolation, verified Codex/OpenCode adapters, PyPI publishing, demo video, CI
execution on GitHub.

## 2026-11-08 — follow-up

- GitHub Actions green on first push (tests matrix: Windows/Linux/macOS × Python
  3.12/3.13; ci: lint, mypy, benchmark controls).
- Fixed: execution records stuck in `running` when an adapter raised.
- Added Alembic (`0001` autogenerated from the models). The development database
  created before Alembic was stamped and remained readable.
- Added Docker sandbox for validation commands. Docker is not installed on the
  development machine: the wrapper and fail-closed behaviour are unit-tested locally;
  the real-container test runs only where Docker exists (GitHub Linux runners).
- Local gate: ruff, mypy strict (78 files) clean; see CI for the latest test count.
