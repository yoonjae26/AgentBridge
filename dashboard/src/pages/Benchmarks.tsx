import { api } from "../api";
import { Card, Empty, ErrorBox, fmt, pct, useData } from "../components/ui";

const METRICS: [string, string, "pct" | "num"][] = [
  ["runs_executed", "Runs executed", "num"],
  ["runs_not_executable", "Not executable", "num"],
  ["task_success_rate", "Task success", "pct"],
  ["test_pass_rate", "Hidden test pass", "pct"],
  ["mean_execution_time_seconds", "Mean time (s)", "num"],
  ["total_estimated_cost_usd", "Est. cost (USD)", "num"],
  ["total_measured_cost_usd", "Measured cost (USD)", "num"],
  ["total_input_tokens", "Input tokens", "num"],
  ["total_output_tokens", "Output tokens", "num"],
  ["regression_rate", "Regression", "pct"],
  ["retry_rate", "Retries / run", "num"],
  ["failure_rate", "Failure", "pct"],
  ["merge_success_rate", "Merge success", "pct"],
];

export function BenchmarksPage() {
  const { data, error } = useData(() => api.benchmarks(), []);
  return (
    <div className="stack">
      <p className="note">
        Values come only from saved experiment records. <strong>n/a</strong> means the metric
        was not available — it is never treated as zero. <code>mock-*</code> configurations are
        harness controls and say nothing about AI agent quality.
      </p>
      <ErrorBox error={error} />
      {data && data.length === 0 && (
        <Empty>No experiments found. Run <code>agentbridge benchmark run smoke -c mock-oracle
          -c mock-noop</code>.</Empty>
      )}
      {data?.map((exp) => {
        const configs = Object.keys(exp.summary);
        return (
          <Card key={`${exp.location}/${exp.id}`} title={<code>{exp.id}</code>}
            actions={<span className="muted">{exp.location} · suite {exp.suite ?? "n/a"} ·
              reps {exp.repetitions ?? "n/a"}</span>}>
            <div className="bars">
              {configs.map((c) => {
                const rate = exp.summary[c].task_success_rate;
                return (
                  <div key={c} className="bar-row">
                    <span className="bar-label">{c}</span>
                    <div className="bar-track">
                      {rate === null || rate === undefined
                        ? <span className="muted small">not available</span>
                        : <div className="bar-fill" style={{ width: `${rate * 100}%` }} />}
                    </div>
                    <span className="bar-value">{pct(rate)}</span>
                  </div>
                );
              })}
            </div>
            <div className="table-wrap"><table>
              <thead><tr><th>Metric</th>{configs.map((c) => <th key={c}>{c}</th>)}</tr></thead>
              <tbody>
                {METRICS.map(([key, label, kind]) => (
                  <tr key={key}><td>{label}</td>
                    {configs.map((c) => {
                      const v = exp.summary[c][key];
                      return <td key={c}>{kind === "pct" ? pct(v) : fmt(v)}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table></div>
          </Card>
        );
      })}
    </div>
  );
}
