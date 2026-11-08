---
name: agentbridge
description: Delegate coding work through AgentBridge so every change lands on its own git branch, is checked by real lint/type/test runs, and merges only after the human approves. Use when the user asks to "run this through AgentBridge", wants a change isolated and verified before it touches their branch, or asks for the status, report, logs or review of an AgentBridge task.
---

# AgentBridge

AgentBridge (`pip install agentbridge-core`, command `agentbridge`) runs an objective
as tasks, gives each task its own git worktree and branch, runs lint, type checks,
tests and a diff review itself, and then stops at `WAITING_FOR_APPROVAL`.

**The one rule: you never approve.** Merging is the human's decision. Do not run
`agentbridge tasks approve`, do not merge or cherry-pick AgentBridge branches yourself,
and do not edit files inside `.agentbridge/worktrees/`. Present the evidence and let
the user approve.

## 1. Check the setup

```bash
agentbridge --version            # not found → ask the user to: pip install agentbridge-core
git rev-parse --show-toplevel    # must be inside a git repository with at least one commit
```

If `agentbridge.yaml` does not exist at the repository root, ask before running
`agentbridge init`: it creates `agentbridge.yaml` and `.agentbridge/`.

Then:

```bash
agentbridge providers check --json   # exit 3 = a provider is unavailable
```

Use the provider the user names. If they named none, use the project's configured
default. The `mock` provider is free and only for trying the flow; `claude` runs Claude
Code with the user's own account and costs usage. Say which provider you will use
before a paid run.

## 2. Run the objective

Write one concrete objective with the acceptance criteria in it, then:

```bash
agentbridge run "<objective>" --provider <name> --json
```

- Output: `{"run_id": "...", "tasks": {"<task_id>": "<STATUS>", ...}}`.
- Real agent runs can take minutes: use a long command timeout (10 minutes) or run it
  in the background and wait for it to exit.
- Never pass `--policy trusted` unless the user asked for it.

## 3. Read the evidence

For each task id:

```bash
agentbridge report <task_id> --format json
```

stdout is one JSON object. The fields that matter:

| Field | Meaning |
|---|---|
| `task.status` | `WAITING_FOR_APPROVAL`, `FAILED`, `CANCELLED`, `SUCCEEDED`, ... |
| `task.git_branch`, `task.changed_files` | Where the work is and what it touched |
| `validation.outcome` | `PASS`, `WARNING`, `FAIL` or `NEEDS_HUMAN_REVIEW` |
| `validation.steps[]` | `name` (diff, scope, isolation, lint, type_check, tests, review) and `outcome` |
| `validation.tests_passed`, `validation.tests_failed` | Counts from the real test run |
| `task.error_message` | Why a task failed |
| `next_steps` | What AgentBridge suggests |

To see the change itself: `git diff <task.base_commit> <task.head_commit>`.
For history and the agent's own output: `agentbridge logs <task_id> --tail 80`.

## 4. Report to the user

Give a short summary per task. Report what the checks show, not what the agent said:

- status and validation outcome, with every step that is not `PASS` and why
- tests passed / failed, as numbers
- changed files, and a short description of the diff
- anything outside the expected scope

Then hand over the decision with the exact commands:

```bash
agentbridge tasks approve <task_id>                     # merge into the base branch
agentbridge tasks reject <task_id> --reason "<why>"     # keep the branch, do not merge
```

If validation is `FAIL`, say so plainly and do not suggest approving. Offer
`agentbridge tasks resume <task_id>` only after the cause is understood.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | Task failed |
| 2 | Configuration error (e.g. no `agentbridge.yaml`) |
| 3 | Provider unavailable |
| 4 | Validation failed |
| 5 | Not found (wrong task or run id) |
| 6 | Blocked by security policy |
| 7 | Invalid state for this action |
| 8 | Git error |
| 130 | Cancelled |

## Don'ts

- Don't approve, merge, force-push, reset or delete AgentBridge branches.
- Don't describe a task as done or working unless `validation.outcome` and the test
  counts say so.
- Don't read, print or copy credentials, `.env` files or tokens; AgentBridge never
  needs them in a command line.
