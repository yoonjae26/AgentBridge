# Troubleshooting

**`No agentbridge.yaml found`** — run `agentbridge init` in the repository (or a
parent directory of where you are).

**`The repository has no commits`** — worktrees need a base commit:
`git add -A && git commit -m "initial commit"`.

**`claude ... unavailable: 'claude' not found on PATH`** — install Claude Code or set
`providers.claude.command` to the full path of the executable.

**Claude runs but the agent says it could not run tests** — expected under the
`standard` policy: `acceptEdits` lets the agent edit files but does not approve shell
commands. AgentBridge runs lint, type checks and tests itself during validation.

**Validation `tests: WARNING No tests were collected`** — pytest exit code 5. Add
tests or set `validation.run_tests: false`.

**`type_check: WARNING There are no .py[i] files`** — the repository has no Python
files; set `validation.run_type_check: false` or change `type_check_command`.

**`Skipped: tool unavailable (No module named ruff)`** — the validation interpreter
lacks the tool. Install it (`pip install ruff mypy pytest`) or point the command at
your project's environment (e.g. `["uv", "run", "pytest", "-q"]` plus
`security.extra_allowed_commands: [uv]`).

**`Blocked by policy: Executable 'x' is not allowed`** — add the executable to
`security.extra_allowed_commands` if it is safe for your project.

**`tasks approve` refuses: primary working tree has uncommitted changes** — commit or
stash your own tracked changes first; AgentBridge never overwrites them.

**`tasks approve` refuses: checkout is on another branch** — `git switch <base>`.

**`Merge would conflict in: ...`** — resolve manually: `git merge <task-branch>` in
your checkout, fix, commit; then reject the task or keep it for reference.

**Task stuck in `RUNNING` after a crash** — any `agentbridge tasks list` after
`stale_after_seconds` marks it `INTERRUPTED`. Then `agentbridge tasks resume <id>`
(validates existing work) or `--rerun` (executes the agent again).

**Windows: long paths** — enable long paths (`git config --system core.longpaths true`)
if worktrees fail to check out deeply nested repositories.

**Where are logs?** `agentbridge logs <task_id>`, `.agentbridge/logs/<task_id>.log`,
raw agent output in `.agentbridge/artifacts/<task_id>/`.

**`No benchmark tasks directory`** — benchmark data lives in the source repository
(`benchmarks/`) and is not part of the wheel. Run from a source checkout, pass
`--benchmarks-dir /path/to/benchmarks`, or set `AGENTBENCH_DIR`.
