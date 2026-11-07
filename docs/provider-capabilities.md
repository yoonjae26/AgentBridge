# Provider capability matrix

Verified on 2026-11-07 on Windows 11 with Python 3.12.7 and Git 2.53.0. "Verified"
means exercised by AgentBridge in this environment; "Tested" means covered by the
automated test suite with a fake executable.

| Capability / operation | Mock | Claude Code CLI | Antigravity remote | Generic CLI |
|---|---|---|---|---|
| Availability check | Yes | Yes (`claude --version`) | CLI presence only | Executable on PATH |
| Authentication check | n/a | Presence of `ANTHROPIC_API_KEY` or `~/.claude/.credentials.json` (never read); otherwise `unknown` | Not checked | Not checked |
| Non-interactive execution | Simulated | **Verified** (`claude -p --output-format json --permission-mode <mode>`, prompt on stdin) | **No** — manual handoff | User-defined |
| Local workspace | Yes | Yes (`cwd` = task worktree) | **No** — works on the hosted repository | Yes |
| Structured output | Yes | Yes (JSON result object) | No | No |
| Plan generation | Yes (fixed template) | Yes (JSON plan, validated) | No | No |
| Review | Yes (always PASS; simulated) | Yes | No | If declared |
| Timeout | Yes | Yes (process tree killed) | n/a | Yes |
| Cancellation | Yes | Yes (process tree killed) | No | Yes |
| Status after restart | In-process only | **No** | No | No |
| Token usage | No | Yes (`usage`; input = input + cache creation + cache read) | No | No |
| Cost | No | CLI estimate `total_cost_usd` (labelled *estimated*) | No | No |
| Model metadata | n/a | `modelUsage` key | No | No |

## Claude Code details (verified with 2.1.303)

- `-p/--print`, `--output-format json|stream-json|text`, `--permission-mode
  acceptEdits|auto|bypassPermissions|manual|dontAsk|plan`, `--model`, `--allowedTools`
  were confirmed in `claude --help`.
- AgentBridge uses `acceptEdits` for editing tasks and `plan` for read-only tasks
  (analysis, review, SAFE policy). In `acceptEdits` mode shell commands are not
  approved in non-interactive runs, so the agent edits files and AgentBridge runs the
  checks. `bypassPermissions` and `--dangerously-skip-permissions` are rejected by the
  configuration validator.
- A real run on 2026-11-07 (one task: create `hello.py` + one test) completed in about
  20 s; the CLI reported usage and an estimated cost, and AgentBridge's own validation
  passed. This is a smoke check, not a benchmark result.

## Google Antigravity remote agents

AgentBridge could not verify a documented, stable headless task API, local MCP
support or machine-readable output for Antigravity remote agents, and the `agy` CLI
was not installed in the development environment. Therefore:

- **Supported:** generating a task packet (JSON + Markdown) with repository URL
  (credentials stripped), base branch and commit, acceptance criteria, prompt and the
  expected result branch; importing a result branch through `git fetch`; validating it
  locally; approval-gated merge.
- **Manual:** starting the remote session, authentication, monitoring it.
- **Not supported:** automated execution, cancellation, status, token or cost data.

AgentBridge never reports a remote task as executed: the execution record says
`handoff_prepared` and the task waits with reason `remote_handoff`.
See [providers.md](providers.md#antigravity-remote-handoff).
