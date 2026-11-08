# AgentBridge skill

A free [Agent Skill](https://docs.anthropic.com/en/docs/claude-code/skills) that teaches
a coding agent to delegate work through the real
[AgentBridge](https://github.com/yoonjae26/AgentBridge) CLI: each change runs on its own
git branch, is verified by actual lint, type and test runs, and **merges only when you
approve it.**

The skill is instructions; the guarantees come from the AgentBridge CLI it drives.

## Install

1. Install the CLI with your own account setup:

   ```bash
   pip install agentbridge-core
   ```

2. Copy this folder into your agent's skills directory. For Claude Code:

   ```bash
   # personal, all projects
   cp -r skills/agentbridge ~/.claude/skills/agentbridge
   # or only this project
   cp -r skills/agentbridge .claude/skills/agentbridge
   ```

3. **Recommended:** make approval a human-only action by denying it to the agent in
   `.claude/settings.json`:

   ```json
   {
     "permissions": {
       "deny": ["Bash(agentbridge tasks approve:*)"]
     }
   }
   ```

   The skill already tells the agent never to approve; the deny rule enforces it.

## Use

Ask your agent, for example:

> Run "add input validation to the signup form, with tests" through AgentBridge.

The agent checks the setup, runs the objective, reads the JSON report, and gives
you the validation results, test counts and changed files. Then it gives you the
`approve` / `reject` commands to run yourself.

## Cost

`--provider mock` is free and only for trying the flow. `--provider claude` runs Claude
Code with **your** account and uses your plan or API credits.

MIT licensed, like AgentBridge.
