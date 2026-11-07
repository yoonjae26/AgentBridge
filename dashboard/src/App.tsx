import { useCallback, useEffect, useRef, useState } from "react";
import { api, LiveEvent, Session } from "./api";
import { ErrorBox, Link } from "./components/ui";
import { BenchmarksPage } from "./pages/Benchmarks";
import { RunDetailPage, RunsPage, TasksPage } from "./pages/Lists";
import { OverviewPage } from "./pages/Overview";
import { TaskDetailPage } from "./pages/TaskDetail";

function useHashRoute(): string {
  const [hash, setHash] = useState(window.location.hash.slice(1) || "/");
  useEffect(() => {
    const onChange = () => setHash(window.location.hash.slice(1) || "/");
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

/** Subscribes to server-sent events; bumps `version` (debounced) so pages refetch. */
function useLive() {
  const [version, setVersion] = useState(0);
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  const bump = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setVersion((v) => v + 1), 300);
  }, []);
  useEffect(() => {
    const source = new EventSource("/api/events/stream");
    source.addEventListener("hello", () => setConnected(true));
    source.addEventListener("task", (e) => {
      const ev = JSON.parse((e as MessageEvent).data) as LiveEvent;
      setEvents((list) => [ev, ...list].slice(0, 200));
      bump();
    });
    source.onerror = () => setConnected(false);
    return () => source.close();
  }, [bump]);
  return { version, events, connected, refresh: bump };
}

const NAV = [
  ["/", "Overview"], ["/runs", "Runs"], ["/tasks", "Tasks"], ["/benchmarks", "AgentBench"],
] as const;

export function App() {
  const route = useHashRoute();
  const live = useLive();
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => { api.session().then(setSession, setError); }, []);

  const [path, query] = route.split("?");
  const params = new URLSearchParams(query ?? "");
  const parts = path.split("/").filter(Boolean);

  let page;
  if (parts[0] === "tasks" && parts[1]) {
    page = <TaskDetailPage id={decodeURIComponent(parts[1])} version={live.version}
      refresh={live.refresh} />;
  } else if (parts[0] === "tasks") {
    page = <TasksPage version={live.version} status={params.get("status") ?? ""} />;
  } else if (parts[0] === "runs" && parts[1]) {
    page = <RunDetailPage id={decodeURIComponent(parts[1])} version={live.version} />;
  } else if (parts[0] === "runs") {
    page = <RunsPage version={live.version} />;
  } else if (parts[0] === "benchmarks") {
    page = <BenchmarksPage />;
  } else {
    page = <OverviewPage version={live.version} events={live.events} />;
  }
  const active = "/" + (parts[0] ?? "");

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">AgentBridge</div>
        <nav>
          {NAV.map(([to, label]) => (
            <Link key={to} to={to} className={active === to ? "nav active" : "nav"}>{label}</Link>
          ))}
        </nav>
        <div className="meta">
          {session && <span>{session.project} · v{session.version}</span>}
          <span className={live.connected ? "conn on" : "conn off"}>
            {live.connected ? "live" : "offline"}
          </span>
        </div>
      </header>
      <main>
        <ErrorBox error={error} />
        {page}
      </main>
    </div>
  );
}
