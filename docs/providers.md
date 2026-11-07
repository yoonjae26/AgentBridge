# Providers

A provider is a configured instance of an adapter type. Adapters implement
`agentbridge.agents.base.AgentAdapter`:

```python
class AgentAdapter(ABC):
    async def check_availability(self) -> AvailabilityReport: ...
    async def get_capabilities(self) -> ProviderCapabilities: ...
    async def execute(self, request: ExecutionRequest) -> ExecutionResult: ...
    async def get_status(self, execution_id: str) -> ExecutionState: ...  # default UNKNOWN
    async def cancel(self, execution_id: str) -> bool: ...
```

All inputs and outputs are Pydantic models. Unsupported operations are declared as
such in `ProviderCapabilities` (`execution`, `cancellation`, `status_query` are
`supported`, `unsupported`, `experimental` or `manual`). Usage fields are `None` when
unknown — never zero.

## Mock

Deterministic and free. Use it for development, CI and demos.

```bash
agentbridge run "anything" --provider mock --mock-scenario failure
```

Scenarios: `success` (writes `providers.mock.files` or a placeholder file),
`failure` (retryable), `delay` (cancellable sleep), `interrupt`, `invalid_output`,
`unavailable`. Planner role returns a three-task plan; reviewer role returns
`VERDICT: PASS`. Mock results are labelled as simulated.

## Claude Code

Prerequisites: install Claude Code, run `claude` once to log in (or provide
`ANTHROPIC_API_KEY` in your environment), then `agentbridge providers check`.

AgentBridge runs, in the task worktree:

```text
claude -p --output-format json --permission-mode acceptEdits [--model M] [--allowedTools ...]
```

The prompt is sent on stdin (never on the command line). Output is saved to
`.agentbridge/artifacts/<task_id>/<execution_id>.claude.json` after secret
redaction. Timeouts and cancellation terminate the whole process tree.

## Antigravity remote handoff

1. Configure the provider and route work to it:

   ```yaml
   providers:
     antigravity: {enabled: true, execution_mode: remote_handoff, command: agy, git_remote: origin}
   routing: {planner: mock, default_worker: antigravity}
   ```

2. Make sure the base branch is pushed to the remote the remote agent will use.
3. `agentbridge run "Implement X"` → the task stops in `WAITING_FOR_APPROVAL`
   (`remote_handoff`). Print the packet with `agentbridge remote packet <task_id>`.
4. Launch the remote agent with Antigravity's supported workflow
   (<https://antigravity.google/docs/remote-agents>), give it the packet's prompt and
   ask it to push branch `agentbridge-remote/<task_id>`.
5. Import and validate locally:

   ```bash
   agentbridge remote import <task_id> --branch agentbridge-remote/<task_id> --remote origin
   ```

   The branch is fetched into a new local worktree; AgentBridge checks that it
   descends from the recorded base commit (otherwise `NEEDS_HUMAN_REVIEW`) and runs
   the full validation pipeline.
6. `agentbridge tasks approve <task_id>` or `agentbridge tasks reject <task_id>`.

Recovery: the packet and task state persist; you can import at any later time. If
the remote agent produced nothing usable, reject the task.

## Generic CLI (Codex, OpenCode, custom tools)

```yaml
providers:
  my-agent:                        # hypothetical tool; use your agent's documented flags
    type: generic_cli
    command: my-agent
    args: ["run", "--prompt-file", "{prompt_file}"]   # omit {prompt_file} to use stdin
    capabilities: [edit_code, analyze]
```

No Codex or OpenCode adapter ships in v0.1.0; their command-line flags were not
verified, so no ready-made configuration is provided.

Capabilities are your declaration; AgentBridge cannot verify them. Check the tool's
documentation for its supported non-interactive interface before configuring it.

## Writing a new adapter

1. Subclass `AgentAdapter`, set `provider_type`.
2. Declare only verified capabilities in `get_capabilities`.
3. Return `ExecutionResult` with the correct `ExecutionState` and `retryable` flag.
4. Write raw output to `request.output_dir` and pass text through `security.secrets.redact`.
5. Register the type in `agents/registry.py` and add it to `KNOWN_PROVIDER_TYPES`.
6. Add tests that use a fake executable (see `tests/providers/test_claude_adapter.py`).
