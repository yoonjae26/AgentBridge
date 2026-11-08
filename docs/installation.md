# Installation

## Requirements

- Python 3.12 or newer
- Git 2.38 or newer (`git merge-tree --write-tree` is used for conflict dry runs)
- Optional: Claude Code CLI, logged in (`claude` on PATH)
- Optional: Google Antigravity, for the manual remote handoff workflow

## From source

```bash
git clone https://github.com/yoonjae26/AgentBridge.git
cd AgentBridge
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]" -e packages/agentbridge-bench
agentbridge --version
```

With uv:

```bash
uv venv && uv pip install -e ".[dev]" -e packages/agentbridge-bench
```

Tip for machines with a small system drive: keep the virtual environment and caches
on another drive, e.g. `UV_CACHE_DIR=E:/.uv-cache` or `PIP_CACHE_DIR=E:/.pip-cache`,
and run tests with `pytest --basetemp=E:/tmp/pytest`.

## Initialise a project

```bash
cd /path/to/repo
git log -1            # AgentBridge needs at least one commit
agentbridge init
agentbridge providers check
```

`init` creates `agentbridge.yaml` and `.agentbridge/`, and adds `.agentbridge/` to
`.git/info/exclude` (your `.gitignore` is not modified). Commit `agentbridge.yaml` if
you want it shared; it contains no secrets.

## Verify the installation

```bash
agentbridge run "Create a Python hello world function" --provider mock
agentbridge tasks list
agentbridge report <task_id>
```

Run the project's own checks:

```bash
make check            # or: ruff check src tests && mypy && pytest
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (including tasks waiting for approval) |
| 1 | A task failed or was interrupted |
| 2 | Configuration error |
| 3 | Provider unavailable (`providers check`) |
| 4 | Validation failed |
| 5 | Task or run not found |
| 6 | Blocked by security policy |
| 7 | Invalid state or state transition |
| 8 | Git error |
| 130 | Cancelled / interrupted by the user |
