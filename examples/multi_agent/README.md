# Multi-agent workflow

Uses the `standard` planner: an analyst task, a developer task that starts after it,
and a reviewer task that works on the developer's branch. In addition,
`routing.reviewer` asks an agent to review every editing task's diff during
validation.

```bash
agentbridge providers check            # claude must be available
agentbridge run "Add input validation to the signup handler" --planner standard
agentbridge report <run_id>
```

Notes:

- All roles here use Claude Code, so the review is a *separate session*, not an
  independent vendor. The report marks this ("same provider as worker").
- Swap `routing.roles` to `mock` to try the flow without any account.
- Each role invocation is a separate paid Claude Code run.
