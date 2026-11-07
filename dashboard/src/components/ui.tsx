import { ReactNode, useEffect, useState } from "react";

const TONES: Record<string, string> = {
  SUCCEEDED: "good", PASS: "good", completed: "good",
  FAILED: "bad", FAIL: "bad", failed: "bad", INTERRUPTED: "bad", timed_out: "bad",
  invalid_output: "bad", unavailable: "bad",
  WAITING_FOR_APPROVAL: "warn", WARNING: "warn", NEEDS_HUMAN_REVIEW: "warn",
  handoff_prepared: "warn",
  RUNNING: "info", VALIDATING: "info", INTEGRATING: "info", QUEUED: "info", READY: "info",
  running: "info",
};

export function Badge({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="badge muted">n/a</span>;
  const tone = TONES[value] ?? "muted";
  return <span className={`badge ${tone}`}>{value.replace(/_/g, " ")}</span>;
}

export function Card({ title, children, actions }:
  { title?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head"><h2>{title}</h2><div>{actions}</div></header>
      )}
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const err = error as { message?: string; hint?: string };
  return (
    <div className="error-box" role="alert">
      <strong>{err.message ?? String(error)}</strong>
      {err.hint && <div className="hint">{err.hint}</div>}
    </div>
  );
}

export function fmt(value: unknown): string {
  if (value === null || value === undefined || value === "") return "n/a";
  if (typeof value === "number") return Number.isInteger(value) ? String(value)
    : value.toFixed(value < 1 ? 4 : 2);
  return String(value);
}

export function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "n/a" : `${Math.round(value * 100)}%`;
}

export function ago(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`;
  return new Date(iso).toLocaleString();
}

export function short(sha: string | null | undefined): string {
  return sha ? sha.slice(0, 10) : "n/a";
}

export function Link({ to, children, className }:
  { to: string; children: ReactNode; className?: string }) {
  return <a className={className} href={`#${to}`}>{children}</a>;
}

/** Fetch data, re-fetching whenever `version` (live event counter) changes. */
export function useData<T>(loader: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    let alive = true;
    loader().then(
      (value) => { if (alive) { setData(value); setError(null); } },
      (err) => { if (alive) setError(err); },
    );
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error };
}

export function DiffView({ patch }: { patch: string }) {
  if (!patch.trim()) return <Empty>No changes.</Empty>;
  return (
    <pre className="diff">
      {patch.split("\n").map((line, i) => {
        let cls = "";
        if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("diff ")) {
          cls = "d-file";
        } else if (line.startsWith("@@")) cls = "d-hunk";
        else if (line.startsWith("+")) cls = "d-add";
        else if (line.startsWith("-")) cls = "d-del";
        return <span key={i} className={cls}>{line + "\n"}</span>;
      })}
    </pre>
  );
}
