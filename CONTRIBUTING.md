# Contributing to AgentBridge

Thank you for helping. AgentBridge values correctness, reliability and security over
feature count: a small, well-tested change is better than a large incomplete one.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
make check
```

## Workflow

1. Open an issue for anything non-trivial so the design can be discussed first.
2. Create a branch, keep the change focused, and add tests.
3. Run `make check` (Ruff, format check, Mypy strict, Pytest). All must pass.
4. Update documentation when behaviour changes. Docs must describe what the code does
   today, not what it might do.
5. Add an entry under "Unreleased" in `CHANGELOG.md`.
6. Open a pull request using the template.

## Ground rules

- Never add code that executes text produced by agents, planners or repositories.
- Never weaken a security check to make a test pass.
- Provider adapters must declare only capabilities verified against official
  documentation or the installed tool, and tests must use fake executables (no paid
  API calls in CI).
- Benchmark changes must not fabricate or impute results; unknown values stay `null`.
- New benchmark tasks need a fixture, hidden tests, a reference solution, and must
  pass under `mock-oracle` and fail under `mock-noop`.

## Code style

Ruff (lint + format, line length 100) and Mypy in strict mode for `src/`. Prefer small
modules, typed Pydantic models at boundaries and explicit errors from
`agentbridge.errors`.
