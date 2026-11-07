import { api, Task } from "../api";
import { ago, Badge, Card, Empty, ErrorBox, Link, short, useData } from "../components/ui";

const STATUSES = ["", "WAITING_FOR_APPROVAL", "RUNNING", "VALIDATING", "FAILED",
  "INTERRUPTED", "SUCCEEDED", "CANCELLED", "PENDING"];

export function TaskTable({ tasks }: { tasks: Task[] }) {
  if (tasks.length === 0) return <Empty>No tasks.</Empty>;
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Task</th><th>Title</th><th>Role</th><th>Status</th><th>Provider</th>
          <th>Validation</th><th>Retries</th><th>Created</th></tr></thead>
        <tbody>
          {tasks.map((t) => (
            <tr key={t.id}>
              <td><Link to={`/tasks/${t.id}`}><code>{t.id}</code></Link></td>
              <td className="clip-cell">{t.title}</td>
              <td>{t.role}</td>
              <td><Badge value={t.status} />
                {t.waiting_reason && <div className="muted small">{t.waiting_reason}</div>}</td>
              <td>{t.assigned_provider ?? "n/a"}</td>
              <td><Badge value={t.validation_outcome} /></td>
              <td>{t.retry_count}</td>
              <td className="muted">{ago(t.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TasksPage({ version, status }: { version: number; status: string }) {
  const { data, error } = useData(() => api.tasks(status || undefined), [version, status]);
  return (
    <Card
      title="Tasks"
      actions={
        <select value={status} aria-label="Filter by status"
          onChange={(e) => { window.location.hash = e.target.value
            ? `/tasks?status=${e.target.value}` : "/tasks"; }}>
          {STATUSES.map((s) => <option key={s} value={s}>{s ? s.replace(/_/g, " ")
            : "All statuses"}</option>)}
        </select>
      }
    >
      <ErrorBox error={error} />
      {data ? <TaskTable tasks={data} /> : !error && <p className="loading">Loading…</p>}
    </Card>
  );
}

export function RunsPage({ version }: { version: number }) {
  const { data, error } = useData(() => api.runs(), [version]);
  return (
    <Card title="Runs">
      <ErrorBox error={error} />
      {data && (data.length === 0 ? <Empty>No runs yet.</Empty> : (
        <div className="table-wrap">
          <table>
            <thead><tr><th>Run</th><th>Objective</th><th>Planner</th><th>Tasks</th>
              <th>Base</th><th>Created</th></tr></thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td><Link to={`/runs/${r.id}`}><code>{r.id}</code></Link></td>
                  <td className="clip-cell">{r.objective}</td>
                  <td>{r.planner}</td>
                  <td className="row">{Object.entries(r.statuses).map(([s, n]) =>
                    <span key={s}><Badge value={s} /> {n}</span>)}</td>
                  <td><code>{r.base_branch ?? "n/a"}@{short(r.base_commit)}</code></td>
                  <td className="muted">{ago(r.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </Card>
  );
}

export function RunDetailPage({ id, version }: { id: string; version: number }) {
  const { data, error } = useData(() => api.run(id), [id, version]);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <p className="loading">Loading…</p>;
  return (
    <div className="stack">
      <Card title={<>Run <code>{data.id}</code></>}>
        <p className="objective">{data.objective}</p>
        <dl className="facts">
          <dt>Planner</dt><dd>{data.planner}</dd>
          <dt>Policy</dt><dd>{data.policy}</dd>
          <dt>Base</dt><dd><code>{data.base_branch}@{short(data.base_commit)}</code></dd>
          <dt>Created</dt><dd>{new Date(data.created_at).toLocaleString()}</dd>
        </dl>
        {data.warnings.length > 0 && (
          <ul className="warnings">{data.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
        )}
      </Card>
      <Card title="Task graph">
        <ol className="graph">
          {data.tasks.map((t) => (
            <li key={t.id}>
              <Link to={`/tasks/${t.id}`}><strong>{t.key}</strong></Link> <Badge value={t.status} />
              <span className="muted"> {t.role}</span> — {t.title}
              {t.dependencies.length > 0 && (
                <div className="muted small">after {t.dependencies.map((d) =>
                  d.replace(`${data.id}-`, "")).join(", ")}</div>
              )}
            </li>
          ))}
        </ol>
      </Card>
      <Card title="Tasks"><TaskTable tasks={data.tasks} /></Card>
    </div>
  );
}
