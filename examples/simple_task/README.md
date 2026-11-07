# Simple task with the mock provider

No accounts or API keys needed. The mock provider is deterministic; this example
configures it to write an email validator and its tests so validation has real
checks to run.

```bash
mkdir demo && cd demo
git init -b main
echo "# demo" > README.md
printf '[pytest]\naddopts = -p no:cacheprovider\n' > pytest.ini
git add -A && git commit -m "initial commit"

cp /path/to/agentbridge/examples/simple_task/agentbridge.yaml .
git add agentbridge.yaml && git commit -m "configure agentbridge"

agentbridge providers check
agentbridge run "Add a function that validates email addresses. Write unit tests." --provider mock
agentbridge tasks list
agentbridge report <task_id>          # validation: lint, type check, tests (2 passed)
git status                            # your checkout is unchanged
agentbridge tasks approve <task_id>   # merge only now
```
