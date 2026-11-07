import { useState } from "react";
import { api, ApiError } from "../api";
import {
  ago, Badge, Card, DiffView, Empty, ErrorBox, fmt, Link, short, useData,
} from "../components/ui";

type Action = "approve" | "reject" | "cancel";

const ACTION_TEXT: Record<Action, { label: string; confirm: string; tone: string }> = {
  approve: { label: "Approve & merge", tone: "primary",
             confirm: "Merge this task's branch into the base branch of your checkout?" },
  reject: { label: "Reject", tone: "danger",
            confirm: "Reject this task? Its branch and worktree are kept." },
  cancel: { label: "Cancel", tone: "danger",
            confirm: "Cancel this task? A running agent will be stopped." },
};

function Actions({ id, actions, onDone }:
  { id: string; actions: string[]; onDone: () => void }) {
  const [pending, setPending] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const available = actions.filter((a): a is Action => a in ACTION_TEXT);
  if (available.length === 0) return null;

  async function run(action: Action) {
    setBusy(true); setError(null); setResult(null);
    try {
      const response = await api.action(id, action);
      setResult(response.message);
      setPending(null);
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError(String(err)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="actions">
      {pending ? (
        <div className="confirm">
          <span>{ACTION_TEXT[pending].confirm}</span>
          <button className={ACTION_TEXT[pending].tone} disabled={busy}
            onClick={() => run(pending)}>{busy ? "Working…" : "Yes, continue"}</button>
          <button disabled={busy} onClick={() => setPending(null)}>No</button>
        </div>
      ) : (
        available.map((a) => (
          <button key={a} className={ACTION_TEXT[a].tone} onClick={() => setPending(a)}>
            {ACTION_TEXT[a].label}
          </button>
        ))
      )}
      {result && <div className="ok-box">{result}</div>}
      <ErrorBox error={error} />
    </div>
  );
}

export function TaskDetailPage({ id, version, refresh }:
  { id: string; version: number; refresh: () => void }) {
  const [tab, setTab] = useState<"validation" | "diff" | "output" | "events">("validation");
  const { data, error } = useData(() => api.task(id), [id, version]);
  const diff = useData(() => (tab === "diff" ? api.diff(id) : Promise.resolve(null)),
    [id, tab, version]);
  const output = useData(() => (tab === "output" ? api.output(id) : Promise.resolve(null)),
    [id, tab, version]);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <p className="loading">Loading…</p>;
  const t = data.task;

  return (
    <div className="stack">
      <Card
        title={<><code>{t.id}</code> <Badge value={t.status} /></>}
        actions={<Link to={`/runs/${t.run_id}`}>Run {t.run_id}</Link>}
      >
        <h3 className="title">{t.title}</h3>
        {t.description && t.description !== t.title && <p className="objective">{t.description}</p>}
        <dl className="facts">
          <dt>Role</dt><dd>{t.role}</dd>
          <dt>Provider</dt><dd>{t.assigned_provider ?? "n/a"}</dd>
          <dt>Waiting for</dt><dd>{t.waiting_reason ?? "n/a"}</dd>
          <dt>Validation</dt><dd><Badge value={t.validation_outcome} /></dd>
          <dt>Branch</dt><dd><code>{t.git_branch ?? "n/a"}</code></dd>
          <dt>Base</dt><dd><code>{t.base_branch}@{short(t.base_commit)}</code></dd>
          <dt>Workspace</dt><dd><code className="wrap">{t.workspace_path ?? "n/a"}</code></dd>
          <dt>Retries</dt><dd>{t.retry_count}</dd>
          <dt>Started</dt><dd>{ago(t.started_at)}</dd>
        </dl>
        {t.routing_reason && <p className="muted small">Routing: {t.routing_reason}</p>}
        {t.error_message && <div className="error-box"><strong>Error</strong>
          <pre>{t.error_message}</pre></div>}
        <Actions id={t.id} actions={data.actions} onDone={refresh} />
        {data.next_steps.length > 0 && (
          <ul className="next">{data.next_steps.map((s) => <li key={s}><code>{s}</code></li>)}</ul>
        )}
      </Card>

      {t.acceptance_criteria.length > 0 && (
        <Card title="Acceptance criteria">
          <ul>{t.acceptance_criteria.map((c) => <li key={c}>{c}</li>)}</ul>
        </Card>
      )}

      {t.result_summary && (
        <Card title="Agent summary (unverified — see validation)">
          <pre className="summary">{t.result_summary}</pre>
        </Card>
      )}

      <Card title="Executions">
        {data.executions.length === 0 ? <Empty>No executions.</Empty> : (
          <div className="table-wrap"><table>
            <thead><tr><th>#</th><th>Provider</th><th>Status</th><th>Duration (s)</th>
              <th>Exit</th><th>Model</th><th>Tokens in / out</th><th>Cost (USD)</th></tr></thead>
            <tbody>
              {data.executions.map((e) => (
                <tr key={e.execution_id}>
                  <td>{e.attempt}</td><td>{e.provider}</td><td><Badge value={e.status} /></td>
                  <td>{fmt(e.duration_seconds)}</td><td>{fmt(e.exit_code)}</td>
                  <td>{fmt(e.model)}</td>
                  <td>{fmt(e.input_tokens)} / {fmt(e.output_tokens)}</td>
                  <td>{fmt(e.cost_usd)}{e.cost_source &&
                    <div className="muted small">{e.cost_source}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table></div>
        )}
      </Card>

      <Card title={
        <div className="tabs" role="tablist">
          {(["validation", "diff", "output", "events"] as const).map((name) => (
            <button key={name} role="tab" aria-selected={tab === name}
              className={tab === name ? "tab active" : "tab"} onClick={() => setTab(name)}>
              {name === "diff" ? `Diff (${t.changed_files.length})` : name}
            </button>
          ))}
        </div>
      }>
        {tab === "validation" && (data.validation ? (
          <>
            <p>Overall: <Badge value={data.validation.outcome} /></p>
            <div className="table-wrap"><table>
              <thead><tr><th>Step</th><th>Outcome</th><th>Summary</th><th>Command</th>
                <th>Exit</th><th>s</th></tr></thead>
              <tbody>
                {data.validation.steps.map((s) => (
                  <tr key={s.name}>
                    <td>{s.name}</td><td><Badge value={s.outcome} /></td>
                    <td>{s.summary}
                      {s.output_tail && s.outcome !== "PASS" && (
                        <details><summary>output</summary><pre>{s.output_tail}</pre></details>
                      )}
                      {Array.isArray(s.details.findings) && s.details.findings.length > 0 && (
                        <ul className="small">{(s.details.findings as {severity: string;
                          message: string; path?: string}[]).map((f, i) => (
                          <li key={i}>[{f.severity}] {f.message} {f.path && <code>{f.path}</code>}</li>
                        ))}</ul>
                      )}
                    </td>
                    <td><code className="small">{s.command ? s.command.slice(1).join(" ") : "-"}</code></td>
                    <td>{fmt(s.exit_code)}</td><td>{fmt(s.duration_seconds)}</td>
                  </tr>
                ))}
              </tbody>
            </table></div>
          </>
        ) : <Empty>Validation has not run.</Empty>)}
        {tab === "diff" && (diff.error ? <ErrorBox error={diff.error} /> : !diff.data
          ? <p className="loading">Loading…</p> : !diff.data.available
          ? <Empty>No diff available{diff.data.error ? `: ${diff.data.error}` : ""}.</Empty>
          : <>{diff.data.truncated && <p className="muted">Diff truncated.</p>}
              <DiffView patch={diff.data.patch} /></>)}
        {tab === "output" && (output.data ? (
          output.data.executions.length === 0 ? <Empty>No output.</Empty> :
          output.data.executions.map((e) => (
            <details key={e.execution_id} open={e.attempt === output.data!.executions.length}>
              <summary>Attempt {e.attempt} · <Badge value={e.status} /></summary>
              <pre className="output">{e.output || "(empty)"}</pre>
            </details>
          ))) : <p className="loading">Loading…</p>)}
        {tab === "events" && (
          <ol className="timeline">
            {data.events.map((ev, i) => (
              <li key={i}>
                <span className="muted small">{new Date(ev.at).toLocaleString()}</span>{" "}
                {ev.to ? <><Badge value={ev.from} /> → <Badge value={ev.to} /></>
                  : <span className="muted">{ev.type}</span>}{" "}
                {ev.message}
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
