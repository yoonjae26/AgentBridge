# Task lifecycle

## States

| State | Meaning |
|---|---|
| `PENDING` | Created; waiting for dependencies. |
| `READY` | All dependencies satisfied. |
| `QUEUED` | Scheduled (also used between retry attempts). |
| `RUNNING` | An agent attempt is in progress. |
| `VALIDATING` | AgentBridge is checking the result itself. |
| `WAITING_FOR_APPROVAL` | Needs a human. `waiting_reason` is `merge_approval`, `human_review` or `remote_handoff`. |
| `INTEGRATING` | Merging an approved branch into the base branch. |
| `SUCCEEDED` | Done (merged, or validated with nothing to merge). Terminal. |
| `FAILED` | Execution or validation failed. Re-run only with `tasks resume --rerun`. |
| `CANCELLED` | Cancelled or rejected. Terminal. Branches and worktrees are kept. |
| `INTERRUPTED` | The process died or the outcome is uncertain. |

## Allowed transitions

```text
PENDING              -> READY | FAILED (dependency failed) | CANCELLED
READY                -> QUEUED | FAILED | CANCELLED
QUEUED               -> RUNNING | INTERRUPTED | FAILED | CANCELLED
RUNNING              -> VALIDATING | WAITING_FOR_APPROVAL (remote handoff)
                        | QUEUED (retry) | FAILED | CANCELLED | INTERRUPTED
VALIDATING           -> WAITING_FOR_APPROVAL | SUCCEEDED | FAILED | CANCELLED | INTERRUPTED
WAITING_FOR_APPROVAL -> INTEGRATING (approved) | VALIDATING (remote import / revalidate)
                        | SUCCEEDED (approved, nothing to merge) | CANCELLED (rejected) | FAILED
INTEGRATING          -> SUCCEEDED | FAILED | WAITING_FOR_APPROVAL (merge blocked) | INTERRUPTED
INTERRUPTED          -> QUEUED (explicit rerun) | VALIDATING (recovered work) | CANCELLED | FAILED
FAILED               -> QUEUED (explicit rerun)
```

Any other transition raises `InvalidTransitionError` (exit code 7). Every transition
is stored as an event with the previous and new state.

## Execution attempts and retries

Each attempt has a deterministic id `<task_id>-a<n>` and its own execution record
(timing, exit code, output file, model, tokens, cost when reported). Failures that the
adapter marks as retryable (non-zero exit, timeout, provider error) are retried up to
`orchestration.retry_limit` times, waiting `retry_backoff_seconds * 2^n`. Invalid
output and interruptions are not retried automatically.

## Validation outcome -> next state

| Outcome | Next state |
|---|---|
| `FAIL` | `FAILED` |
| `PASS` / `WARNING` with changes | `WAITING_FOR_APPROVAL` (`merge_approval`) |
| `NEEDS_HUMAN_REVIEW` | `WAITING_FOR_APPROVAL` (`human_review`) |
| No changes (e.g. analysis, review) | `SUCCEEDED` |

## Recovery after a restart

Running tasks update `heartbeat_at` every `heartbeat_seconds`. On `run`, `tasks list`,
`tasks status` and `tasks resume`, tasks in an active state whose heartbeat is older
than `stale_after_seconds` are inspected:

1. If the provider supports status queries and reports the execution as running, the
   task is left alone.
2. Otherwise the outcome is uncertain and the task becomes `INTERRUPTED`.

`agentbridge tasks resume <id>` then:

- validates existing work if the worktree has commits or uncommitted changes (the agent
  is **not** re-run);
- refuses to re-run when the workspace is empty and the outcome is unknown, unless you
  pass `--rerun`;
- for `FAILED` tasks, requires `--rerun`;
- for `WAITING_FOR_APPROVAL`, `--revalidate` commits any manual edits and validates again.

## Cancellation

`agentbridge tasks cancel <id>` sets `cancel_requested`. A running process notices it
on its next heartbeat and terminates the agent process tree. Tasks that are not
running (or whose process is gone) are cancelled immediately. Cancellation is refused
during `INTEGRATING`.
