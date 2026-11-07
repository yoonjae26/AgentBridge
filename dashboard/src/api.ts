export type TaskStatus =
  | "PENDING" | "READY" | "QUEUED" | "RUNNING" | "WAITING_FOR_APPROVAL" | "VALIDATING"
  | "INTEGRATING" | "SUCCEEDED" | "FAILED" | "CANCELLED" | "INTERRUPTED";

export interface Session { token: string; version: string; project: string; root: string }

export interface Provider {
  name: string; type: string; enabled: boolean; execution: string; capabilities: string[];
}

export interface RunSummary {
  id: string; objective: string; planner: string; policy: string;
  base_branch: string | null; base_commit: string | null; created_at: string;
  task_count: number; statuses: Record<string, number>;
}

export interface Overview {
  project: string; policy: string; status_counts: Record<TaskStatus, number>;
  waiting_for_approval: number; providers: Provider[];
  routing: { planner: string; default_worker: string; reviewer: string | null;
             roles: Record<string, string> };
  recent_runs: RunSummary[];
}

export interface Task {
  id: string; run_id: string; key: string; title: string; description: string; role: string;
  status: TaskStatus; assigned_provider: string | null; routing_reason: string | null;
  dependencies: string[]; acceptance_criteria: string[]; expected_files: string[];
  risk_level: string; created_at: string; started_at: string | null;
  completed_at: string | null; retry_count: number; execution_id: string | null;
  workspace_path: string | null; workspace_kind: string | null; git_branch: string | null;
  base_branch: string | null; base_commit: string | null; head_commit: string | null;
  changed_files: string[]; validation_outcome: string | null; waiting_reason: string | null;
  result_summary: string | null; error_message: string | null;
  next_steps?: string[]; actions?: string[];
}

export interface RunDetail extends RunSummary { plan: unknown; warnings: string[]; tasks: Task[] }

export interface Execution {
  execution_id: string; provider: string; attempt: number; status: string;
  started_at: string; finished_at: string | null; duration_seconds: number | null;
  exit_code: number | null; model: string | null; input_tokens: number | null;
  output_tokens: number | null; cost_usd: number | null; cost_source: string | null;
  summary: string | null; error: string | null;
}

export interface Step {
  name: string; outcome: string; summary: string; command: string[] | null;
  exit_code: number | null; duration_seconds: number | null; output_tail: string;
  details: Record<string, unknown>;
}

export interface Validation { outcome: string; steps: Step[]; changed_files: string[] }

export interface TaskEvent {
  at: string; type: string; from: string | null; to: string | null; message: string;
}

export interface TaskReport {
  task: Task; executions: Execution[]; validation: Validation | null;
  events: TaskEvent[]; next_steps: string[]; actions: string[]; notes: string[];
}

export interface Benchmark {
  id: string; location: string; started_at: string | null; suite: string | null;
  repetitions: number | null; summary: Record<string, Record<string, number | null>>;
}

export interface LiveEvent {
  id: number; type: string; task_id: string | null; run_id: string | null;
  to: string | null; message: string; at: string;
}

export class ApiError extends Error {
  hint?: string;
  constructor(message: string, hint?: string) {
    super(message);
    this.hint = hint;
  }
}

let sessionToken = "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === "string" ? detail : detail?.message ?? response.statusText;
    throw new ApiError(message, detail?.hint ?? undefined);
  }
  return body as T;
}

export const api = {
  async session(): Promise<Session> {
    const session = await request<Session>("/api/session");
    sessionToken = session.token;
    return session;
  },
  overview: () => request<Overview>("/api/overview"),
  runs: () => request<RunSummary[]>("/api/runs"),
  run: (id: string) => request<RunDetail>(`/api/runs/${encodeURIComponent(id)}`),
  tasks: (status?: string) =>
    request<Task[]>(`/api/tasks${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  task: (id: string) => request<TaskReport>(`/api/tasks/${encodeURIComponent(id)}`),
  diff: (id: string) =>
    request<{ available: boolean; patch: string; truncated: boolean; error?: string }>(
      `/api/tasks/${encodeURIComponent(id)}/diff`),
  output: (id: string) =>
    request<{ executions: { execution_id: string; attempt: number; status: string;
                            output: string }[] }>(
      `/api/tasks/${encodeURIComponent(id)}/output`),
  benchmarks: () => request<Benchmark[]>("/api/benchmarks"),
  action: (id: string, action: "approve" | "reject" | "cancel", reason?: string) =>
    request<{ message: string; status: string }>(
      `/api/tasks/${encodeURIComponent(id)}/${action}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-AgentBridge-Token": sessionToken },
        body: JSON.stringify(reason ? { reason } : {}),
      }),
};
