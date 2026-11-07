# Dashboard

A local web UI for AgentBridge.

```bash
pip install -e ".[dashboard]"     # FastAPI + uvicorn (already included in [dev])
cd /path/to/your/repo
agentbridge dashboard             # opens http://127.0.0.1:8765/
agentbridge dashboard --port 9000 --no-browser
```

## Pages

- **Overview:** task counts by status, approval banner, recent runs, live activity
  feed, providers with declared capabilities and routing.
- **Runs:** list; run detail with objective, plan warnings and task graph.
- **Tasks:** filter by status; task detail with acceptance criteria, agent summary
  (marked unverified), executions (duration, exit code, model, tokens, cost and its
  source), validation steps with failing output and review findings, the diff, raw
  agent output and the event timeline.
- **AgentBench:** every experiment with a `summary.json` under `benchmarks/reports/`
  and `benchmarks/experiments/`; `n/a` is shown for unavailable metrics.

Pages refresh automatically through server-sent events (`/api/events/stream`), so
runs started from the CLI appear live.

## Actions and security

Approve & merge, Reject and Cancel use exactly the same checks as the CLI (clean
primary checkout, correct branch, conflict dry run, ...), and each asks for
confirmation in the page.

- The server binds to `127.0.0.1` only; `--host` accepts only loopback addresses.
- Requests whose `Host` header is not a loopback name are rejected (DNS rebinding).
- State-changing endpoints require a random per-process token in the
  `X-AgentBridge-Token` header. CORS is never enabled, so other websites cannot obtain
  the token or send the header.
- There is no user authentication: anyone with access to your local machine session
  can use the dashboard, as they could use the CLI.

## Developing the frontend

```bash
cd dashboard
npm install
npm run dev        # Vite dev server, proxies /api to 127.0.0.1:8765
npm run build      # type-checks and writes src/agentbridge/dashboard/static/
```

The built bundle is committed so that users do not need Node.js.
