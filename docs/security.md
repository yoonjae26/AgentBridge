# Security model

## Threat model in one paragraph

AI agents, repository content and tool output are **untrusted input**. AgentBridge
runs agents with your operating-system permissions, so it focuses on (1) never
executing text produced by agents or found in repositories, (2) keeping agent changes
isolated and reviewable until a human approves them, (3) never destroying user work
or history, and (4) keeping credentials out of logs, reports and the database.

**A git worktree is not a sandbox.** An agent process can read and write anything
your user can. `validation.sandbox: docker` runs AgentBridge's own checks (tests,
lint, type checks over agent-written code) in a network-less, capability-dropped,
resource-limited container that fails closed when Docker is missing. Agent processes
are not containerised; use a VM for untrusted repositories.

## Controls

| # | Control | Implementation |
|---|---|---|
| 1 | No hardcoded API keys | Providers authenticate through their own CLIs; config holds no secrets. |
| 2 | No credentials in logs | `security/secrets.redact` is applied to agent output files, summaries, errors, events and stored patches (known token formats, `KEY=value` assignments, bearer tokens, private keys, values of sensitive environment variables). |
| 3 | No untrusted commands | Only commands from `agentbridge.yaml` run, through `permissions.check_command`: no shell, no shell metacharacters, executable allowlist per policy, `python -m` module allowlist, no `python -c`, destructive executables blocked. Objectives, plans and agent output are never executed. |
| 4 | No automatic deletion | AgentBridge never deletes branches; `tasks cleanup` removes only *clean* finished worktrees on request. |
| 5 | No force-push | `git push --force/-f/--force-with-lease/--mirror/--delete` and `+refspec` are refused by the git wrapper; `allow_force_push: true` fails validation. |
| 6 | No automatic merge | `INTEGRATING` is reachable only from `WAITING_FOR_APPROVAL` via `tasks approve`; disabling approval fails validation. |
| 7 | Separate workspaces | One worktree and branch per task; existing branches are never reused or overwritten. |
| 8 | Timeouts | Per task, per provider and per validation command; the process tree is killed. |
| 9 | Command permissions | SAFE / STANDARD / TRUSTED profiles plus `extra_allowed_commands`. |
| 10 | Audit history | Every transition and notable action is an event in SQLite and in `.agentbridge/logs/<task>.log`. |

Additional checks:

- **Isolation check:** `git status` of your primary checkout is compared before and
  after each agent attempt; a change fails validation.
- **Path validation:** planner `expected_files` and mock output paths must be
  relative, without `..`, and outside `.git`, `.ssh`, `.agentbridge`.
- **Diff review:** added credentials fail validation; changes to CI workflows,
  Dockerfiles, `.env`, git metadata files, deleted tests, skipped tests, `eval/exec`,
  `shell=True` and similar require human review.
- **Merge safety:** merging refuses when your checkout has tracked uncommitted
  changes, is on a different branch, or would conflict (dry run with
  `git merge-tree`); a failed merge is aborted.
- **Remote URLs** in handoff packets have embedded credentials stripped.

## Policy profiles

| Profile | Agents may edit | Validation executables | Claude permission mode |
|---|---|---|---|
| `safe` | No (analysis/review only) | python, pytest, ruff, mypy, pyright, git | `plan` |
| `standard` (default) | Yes, in worktrees | above + npm, node, make + `extra_allowed_commands` | `acceptEdits` |
| `trusted` | Yes | above + npx, uv, tox, nox + extras | `acceptEdits` |

Protected git and filesystem operations stay blocked in every profile.

## Remote agents

Remote providers run in the provider's environment under its own permission model.
Do not assume that protects your machine, and do not put secrets in task
descriptions: handoff packets contain the prompt verbatim.

## Known limitations

- Redaction is pattern-based and cannot catch every secret format.
- Agents can read files outside their worktree (OS permissions apply).
- Environment variables are passed to provider CLIs because they need their own
  credentials.

Report vulnerabilities as described in [SECURITY.md](../SECURITY.md).
