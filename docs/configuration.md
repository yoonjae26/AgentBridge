# Configuration

`agentbridge init` writes `agentbridge.yaml` at the repository root. Every field is
validated with Pydantic; unknown keys are rejected with the exact path of the problem.
**Never put credentials in this file.**

```yaml
version: 1

project:
  name: my-project
  repository: .
  default_branch: main

orchestration:
  max_parallel_tasks: 2          # independent tasks may run concurrently
  retry_limit: 2                 # retries for retryable failures
  retry_backoff_seconds: 2.0     # delay = backoff * 2^retry
  task_timeout_seconds: 1800
  require_approval_before_merge: true   # cannot be disabled
  planner_mode: single           # single | standard | provider
  heartbeat_seconds: 5
  stale_after_seconds: 60        # when an active task without heartbeat is "orphaned"

providers:
  claude:
    enabled: true
    execution_mode: cli
    command: claude
    permission_mode: acceptEdits # plan | acceptEdits | default | dontAsk
    model: null                  # optional; passed as --model
    allowed_tools: []            # optional; passed as --allowedTools
    extra_args: []               # permission-bypass flags are rejected
    timeout_seconds: null
  antigravity:
    enabled: false
    execution_mode: remote_handoff
    command: agy
    git_remote: origin
  mock:
    enabled: true
    scenario: success            # success | failure | delay | interrupt | invalid_output | unavailable
    delay_seconds: 0
    files: {}                    # files the mock writes on success (relative paths)
  # Any other CLI agent (hypothetical example; use the tool's documented flags):
  # my-agent:
  #   type: generic_cli
  #   command: my-agent
  #   args: ["run", "--prompt-file", "{prompt_file}"]  # prompt goes to stdin if no {prompt_file}
  #   capabilities: [edit_code, analyze]               # declare only what it really supports

routing:
  planner: mock
  default_worker: mock
  reviewer: null                 # optional independent agent review of every editing task
  roles: {}                      # e.g. {developer: claude, reviewer: mock}

workspace:
  use_git_worktree: true
  worktree_directory: .agentbridge/worktrees
  branch_prefix: agentbridge

validation:
  run_tests: true
  run_lint: true
  run_type_check: true
  test_command: ["{python}", "-m", "pytest", "-q"]
  lint_command: ["{python}", "-m", "ruff", "check", "."]
  type_check_command: ["{python}", "-m", "mypy", "--ignore-missing-imports", "."]
  type_check_blocking: false     # type errors produce WARNING instead of FAIL
  lint_blocking: true
  command_timeout_seconds: 600
  max_changed_files: 200         # more than this needs human review

security:
  policy: standard               # safe | standard | trusted
  require_approval_for_merge: true    # cannot be disabled
  allow_force_push: false             # must be false
  allow_destructive_commands: false   # must be false
  extra_allowed_commands: []          # extra executables validation may run
```

`{python}` in a command resolves to the interpreter running AgentBridge. Point the
commands at your project's own tooling if it uses a different environment, e.g.
`["uv", "run", "pytest", "-q"]` (add `uv` to `extra_allowed_commands` under the
`standard` policy).

## Provider types

A provider's `type` defaults from its name: `claude` → `claude_code`,
`antigravity` → `antigravity_remote`, `mock` → `mock`. Any other name needs an
explicit `type` (`mock`, `claude_code`, `antigravity_remote`, `generic_cli`).

## Common errors

| Message | Fix |
|---|---|
| `No agentbridge.yaml found` | Run `agentbridge init` in the repository. |
| `routing.default_worker refers to provider 'x'` | Define `providers.x` or change routing. |
| `allow_force_push must be false` | Force-push is never supported. |
| `provider 'x' needs an explicit 'type'` | Add `type:` to that provider. |
