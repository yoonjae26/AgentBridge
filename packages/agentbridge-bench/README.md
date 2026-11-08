# agentbridge-bench

**AgentBench**, the evaluation harness of [AgentBridge](https://github.com/yoonjae26/AgentBridge).
It answers one question with data: *does multi-agent collaboration beat a single
agent on real software-engineering tasks, and when?*

```bash
pip install agentbridge-bench          # also installs agentbridge-core
agentbridge-bench list
agentbridge-bench run smoke -c mock-oracle -c mock-noop     # free harness check
agentbridge-bench run core  -c claude-single -c claude-multi -n 3
agentbridge-bench report <experiment_dir>
```

`agentbridge benchmark …` runs the same commands when this package is installed.

- 12 deterministic tasks in 8 categories, with acceptance tests hidden from the agent
  until it has finished.
- Single- and multi-agent configurations, harness controls (`mock-oracle`, `mock-noop`).
- JSON, CSV, Markdown and SVG reports; missing data is reported as `n/a`, never guessed.

Paid configurations run Claude Code with **your own** account. Method and limits:
[benchmark methodology](https://github.com/yoonjae26/AgentBridge/blob/main/docs/benchmark-methodology.md).
Licensed under MIT.
