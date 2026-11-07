import { api, LiveEvent } from "../api";
import { ago, Badge, Card, Empty, ErrorBox, Link, useData } from "../components/ui";

const ORDER = ["RUNNING", "VALIDATING", "WAITING_FOR_APPROVAL", "INTERRUPTED", "FAILED",
  "SUCCEEDED", "CANCELLED", "PENDING", "QUEUED", "READY", "INTEGRATING"] as const;

export function OverviewPage({ version, events }: { version: number; events: LiveEvent[] }) {
  const { data, error } = useData(() => api.overview(), [version]);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <p className="loading">Loading…</p>;
  const total = Object.values(data.status_counts).reduce((a, b) => a + b, 0);
  return (
    <div className="stack">
      {data.waiting_for_approval > 0 && (
        <Link to="/tasks?status=WAITING_FOR_APPROVAL" className="banner">
          {data.waiting_for_approval} task(s) waiting for your approval →
        </Link>
      )}
      <div className="tiles">
        <div className="tile"><span className="tile-label">Total tasks</span>
          <span className="tile-value">{total}</span></div>
        {ORDER.filter((s) => data.status_counts[s] > 0 || ["RUNNING", "FAILED",
          "SUCCEEDED", "WAITING_FOR_APPROVAL"].includes(s)).map((s) => (
          <Link key={s} to={`/tasks?status=${s}`} className="tile">
            <span className="tile-label"><Badge value={s} /></span>
            <span className="tile-value">{data.status_counts[s] ?? 0}</span>
          </Link>
        ))}
      </div>
      <div className="grid-2">
        <Card title="Recent runs" actions={<Link to="/runs">All runs</Link>}>
          {data.recent_runs.length === 0 ? (
            <Empty>No runs yet. Try <code>agentbridge run "…" --provider mock</code>.</Empty>
          ) : (
            <ul className="list">
              {data.recent_runs.map((run) => (
                <li key={run.id}>
                  <Link to={`/runs/${run.id}`}><strong>{run.id}</strong></Link>
                  <span className="muted"> · {ago(run.created_at)} · {run.planner}</span>
                  <div className="clip">{run.objective}</div>
                  <div className="row">
                    {Object.entries(run.statuses).map(([s, n]) => (
                      <span key={s}><Badge value={s} /> {n}</span>
                    ))}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card title={<>Live activity <span className="live-dot" title="live" /></>}>
          {events.length === 0 ? <Empty>Waiting for events…</Empty> : (
            <ul className="feed">
              {events.slice(0, 40).map((ev) => (
                <li key={ev.id}>
                  <span className="muted">{new Date(ev.at).toLocaleTimeString()}</span>{" "}
                  {ev.task_id && <Link to={`/tasks/${ev.task_id}`}>{ev.task_id}</Link>}{" "}
                  {ev.to ? <Badge value={ev.to} /> : <span className="muted">{ev.type}</span>}{" "}
                  <span>{ev.message}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <Card title="Providers" actions={<span className="muted">policy: {data.policy}</span>}>
        <table>
          <thead><tr><th>Name</th><th>Type</th><th>Enabled</th><th>Execution</th>
            <th>Declared capabilities</th></tr></thead>
          <tbody>
            {data.providers.map((p) => (
              <tr key={p.name}>
                <td><strong>{p.name}</strong></td><td>{p.type}</td>
                <td>{p.enabled ? "yes" : "no"}</td><td>{p.execution}</td>
                <td className="caps">{p.capabilities.map((c) => <code key={c}>{c}</code>)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="muted small">Routing: planner={data.routing.planner}, worker=
          {data.routing.default_worker}, reviewer={data.routing.reviewer ?? "none"}</p>
      </Card>
    </div>
  );
}
