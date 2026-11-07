# Antigravity remote handoff

AgentBridge does **not** start Antigravity remote agents (no verified headless API).
It prepares a task packet, and validates the result you bring back through git.

```bash
git remote -v                         # the repository must be on a hosted remote
git push origin main                  # the base commit must exist on the remote
agentbridge run "Add a /health endpoint with a test"
# -> task waits in WAITING_FOR_APPROVAL (remote_handoff)
agentbridge remote packet <task_id>   # instructions + prompt for the remote agent
```

Launch a remote agent with Antigravity (https://antigravity.google/docs/remote-agents),
paste the prompt, and ask it to push `agentbridge-remote/<task_id>`. Then:

```bash
agentbridge remote import <task_id> --branch agentbridge-remote/<task_id> --remote origin
agentbridge report <task_id>
agentbridge tasks approve <task_id>   # or: agentbridge tasks reject <task_id>
```

Without Antigravity you can rehearse the flow by pushing a branch with that name
yourself.
