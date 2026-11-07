"""Local web dashboard (FastAPI) for AgentBridge.

Security model:
- Binds to 127.0.0.1 by default and rejects requests whose Host header is not a
  loopback name (DNS-rebinding protection).
- Read endpoints are open to the local user. State-changing endpoints (approve,
  reject, cancel) require the per-process token in the ``X-AgentBridge-Token``
  header. Browsers cannot attach that header cross-site without CORS, which this
  server never enables, so other web pages cannot trigger actions.
- Approve goes through the same ``Orchestrator.approve`` checks as the CLI.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select

from agentbridge import __version__
from agentbridge.agents.registry import AgentRegistry
from agentbridge.bench.dataset import default_benchmarks_dir
from agentbridge.config.loader import ProjectPaths
from agentbridge.config.settings import Settings
from agentbridge.core.orchestrator import Orchestrator
from agentbridge.errors import AgentBridgeError, NotFoundError
from agentbridge.reporting.generator import build_task_report, next_steps, task_dict
from agentbridge.security.secrets import redact
from agentbridge.storage.database import Database, EventRecord, RunRecord, TaskRecord
from agentbridge.storage.repositories import Store
from agentbridge.tasks.models import TaskStatus
from agentbridge.workspace.git import Git

STATIC_DIR = Path(__file__).parent / "static"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]", "testserver"}
MAX_DIFF_CHARS = 300_000
MAX_OUTPUT_CHARS = 60_000


class ActionBody(BaseModel):
    reason: str | None = None


class DashboardState:
    def __init__(self, paths: ProjectPaths, settings: Settings, token: str) -> None:
        self.paths = paths
        self.settings = settings
        self.token = token
        self.db = Database(paths.database)
        self.store = Store(self.db)

    def orchestrator(self) -> Orchestrator:
        return Orchestrator(self.paths, self.settings, self.store)


def _error(exc: AgentBridgeError) -> HTTPException:
    status = 404 if isinstance(exc, NotFoundError) else 409
    return HTTPException(status_code=status, detail={"message": exc.message, "hint": exc.hint})


def create_app(
    paths: ProjectPaths,
    settings: Settings,
    *,
    token: str | None = None,
    benchmarks_dir: Path | None = None,
) -> FastAPI:
    state = DashboardState(paths, settings, token or secrets.token_urlsafe(24))
    bench_root = benchmarks_dir or default_benchmarks_dir()
    app = FastAPI(title="AgentBridge Dashboard", version=__version__, docs_url=None,
                  redoc_url=None, openapi_url=None)
    app.state.dashboard = state

    @app.middleware("http")
    async def loopback_only(request: Request, call_next: Any) -> Response:
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].lower()
        if host not in LOOPBACK_HOSTS:
            return JSONResponse({"detail": "Dashboard only serves loopback hosts"}, 403)
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def require_token(x_agentbridge_token: str | None = Header(default=None)) -> None:
        if not x_agentbridge_token or not secrets.compare_digest(
            x_agentbridge_token, state.token
        ):
            raise HTTPException(status_code=403, detail={"message": "Missing or invalid token"})

    # ------------------------------------------------------------ read API
    @app.get("/api/session")
    def session() -> dict[str, Any]:
        return {"token": state.token, "version": __version__,
                "project": settings.project.name, "root": str(paths.root)}

    @app.get("/api/overview")
    def overview() -> dict[str, Any]:
        state.orchestrator().recover()
        with state.db.session() as s:
            counts = dict(
                s.execute(select(TaskRecord.status, func.count()).group_by(TaskRecord.status))
                .tuples()
                .all()
            )
            runs = list(s.scalars(select(RunRecord).order_by(RunRecord.created_at.desc())
                                  .limit(10)))
        registry = AgentRegistry(settings)
        providers = []
        for name in registry.names():
            adapter = registry.get(name, require_enabled=False)
            caps = asyncio.run(adapter.get_capabilities())
            providers.append({
                "name": name,
                "type": adapter.provider_type,
                "enabled": registry.is_enabled(name),
                "execution": caps.execution.value,
                "capabilities": sorted(c.value for c in caps.capabilities),
            })
        return {
            "project": settings.project.name,
            "policy": settings.security.policy.value,
            "status_counts": {s.value: counts.get(s.value, 0) for s in TaskStatus},
            "waiting_for_approval": counts.get(TaskStatus.WAITING_FOR_APPROVAL.value, 0),
            "providers": providers,
            "routing": settings.routing.model_dump(),
            "recent_runs": [_run_summary(state.store, r) for r in runs],
        }

    @app.get("/api/runs")
    def runs(limit: int = Query(50, ge=1, le=500)) -> list[dict[str, Any]]:
        with state.db.session() as s:
            records = list(s.scalars(select(RunRecord).order_by(RunRecord.created_at.desc())
                                     .limit(limit)))
        return [_run_summary(state.store, r) for r in records]

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict[str, Any]:
        try:
            run = state.store.get_run(run_id)
        except AgentBridgeError as exc:
            raise _error(exc) from exc
        summary = _run_summary(state.store, run)
        summary["plan"] = run.plan
        summary["warnings"] = run.warnings
        summary["tasks"] = [_task_row(t) for t in state.store.list_tasks(run_id=run_id)]
        return summary

    @app.get("/api/tasks")
    def tasks(
        status: str | None = None,
        run: str | None = None,
        limit: int = Query(200, ge=1, le=1000),
    ) -> list[dict[str, Any]]:
        statuses = [TaskStatus(status)] if status else None
        return [_task_row(t) for t in state.store.list_tasks(run_id=run, statuses=statuses,
                                                             limit=limit)]

    @app.get("/api/tasks/{task_id}")
    def task_detail(task_id: str) -> dict[str, Any]:
        try:
            task = state.store.find_task(task_id)
        except AgentBridgeError as exc:
            raise _error(exc) from exc
        report = build_task_report(state.store, task.id)
        report["actions"] = _allowed_actions(task)
        return report

    @app.get("/api/tasks/{task_id}/diff")
    def task_diff(task_id: str) -> dict[str, Any]:
        try:
            task = state.store.find_task(task_id)
        except AgentBridgeError as exc:
            raise _error(exc) from exc
        if not task.base_commit or not (task.git_branch or task.head_commit):
            return {"available": False, "patch": "", "truncated": False}
        target = task.head_commit or task.git_branch or ""
        result = Git(paths.root).run("diff", "--no-renames", task.base_commit, target,
                                     check=False)
        if result.returncode != 0:
            return {"available": False, "patch": "", "truncated": False,
                    "error": result.stderr.strip()[:500]}
        patch = result.stdout
        return {"available": True, "patch": redact(patch[:MAX_DIFF_CHARS]),
                "truncated": len(patch) > MAX_DIFF_CHARS}

    @app.get("/api/tasks/{task_id}/output")
    def task_output(task_id: str) -> dict[str, Any]:
        try:
            task = state.store.find_task(task_id)
        except AgentBridgeError as exc:
            raise _error(exc) from exc
        outputs = []
        for execution in state.store.list_executions(task.id):
            text = ""
            path = Path(execution.output_path) if execution.output_path else None
            if path and path.is_file() and path.resolve().is_relative_to(
                paths.state_dir.resolve()
            ):
                text = path.read_text(encoding="utf-8", errors="replace")[-MAX_OUTPUT_CHARS:]
            outputs.append({"execution_id": execution.id, "attempt": execution.attempt,
                            "status": execution.status, "output": redact(text)})
        return {"executions": outputs}

    @app.get("/api/benchmarks")
    def benchmarks() -> list[dict[str, Any]]:
        found = []
        for parent in (bench_root / "reports", bench_root / "experiments"):
            if not parent.is_dir():
                continue
            for directory in sorted(parent.iterdir(), reverse=True):
                summary_file = directory / "summary.json"
                if not summary_file.is_file():
                    continue
                metadata_file = directory / "metadata.json"
                metadata = (json.loads(metadata_file.read_text(encoding="utf-8"))
                            if metadata_file.is_file() else {})
                found.append({
                    "id": directory.name,
                    "location": parent.name,
                    "summary": json.loads(summary_file.read_text(encoding="utf-8")),
                    "started_at": metadata.get("started_at"),
                    "suite": metadata.get("suite"),
                    "repetitions": metadata.get("repetitions"),
                })
        return found

    # --------------------------------------------------------- live updates
    @app.get("/api/events/stream")
    async def event_stream(request: Request, after: int = 0) -> StreamingResponse:
        async def generate() -> AsyncIterator[str]:
            last = after
            if last == 0:
                with state.db.session() as s:
                    last = int(s.scalar(select(func.max(EventRecord.id))) or 0)
            yield f"event: hello\ndata: {json.dumps({'last_id': last})}\n\n"
            idle = 0
            while not await request.is_disconnected():
                with state.db.session() as s:
                    new = list(s.scalars(select(EventRecord).where(EventRecord.id > last)
                                         .order_by(EventRecord.id).limit(200)))
                for ev in new:
                    last = ev.id
                    payload = {"id": ev.id, "type": ev.type, "task_id": ev.task_id,
                               "run_id": ev.run_id, "to": ev.to_status,
                               "message": ev.message, "at": ev.created_at}
                    yield f"event: task\ndata: {json.dumps(payload)}\n\n"
                idle = 0 if new else idle + 1
                if idle and idle % 15 == 0:
                    yield ": keep-alive\n\n"
                await asyncio.sleep(1.0)

        return StreamingResponse(generate(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    # -------------------------------------------------------------- actions
    @app.post("/api/tasks/{task_id}/approve", dependencies=[Depends(require_token)])
    def approve(task_id: str) -> dict[str, Any]:
        try:
            task = state.store.find_task(task_id)
            message = state.orchestrator().approve(task.id)
        except AgentBridgeError as exc:
            raise _error(exc) from exc
        return {"message": message, "status": state.store.get_task(task.id).status}

    @app.post("/api/tasks/{task_id}/reject", dependencies=[Depends(require_token)])
    def reject(task_id: str, body: ActionBody | None = None) -> dict[str, Any]:
        try:
            task = state.store.find_task(task_id)
            state.orchestrator().reject(task.id, (body.reason if body else None)
                                        or "Rejected from dashboard")
        except AgentBridgeError as exc:
            raise _error(exc) from exc
        return {"message": "Rejected; branch kept", "status": "CANCELLED"}

    @app.post("/api/tasks/{task_id}/cancel", dependencies=[Depends(require_token)])
    def cancel(task_id: str) -> dict[str, Any]:
        try:
            task = state.store.find_task(task_id)
            message = state.orchestrator().request_cancel(task.id)
        except AgentBridgeError as exc:
            raise _error(exc) from exc
        return {"message": message, "status": state.store.get_task(task.id).status}

    # -------------------------------------------------------------- frontend
    if (STATIC_DIR / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets", check_dir=False),
                  name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            return FileResponse(STATIC_DIR / "index.html")

    return app


def _run_summary(store: Store, run: RunRecord) -> dict[str, Any]:
    tasks = store.list_tasks(run_id=run.id)
    statuses: dict[str, int] = {}
    for task in tasks:
        statuses[task.status] = statuses.get(task.status, 0) + 1
    return {"id": run.id, "objective": run.objective, "planner": run.planner,
            "policy": run.policy, "base_branch": run.base_branch,
            "base_commit": run.base_commit, "created_at": run.created_at,
            "task_count": len(tasks), "statuses": statuses}


def _task_row(task: TaskRecord) -> dict[str, Any]:
    row = task_dict(task)
    row["next_steps"] = next_steps(task)
    row["actions"] = _allowed_actions(task)
    return row


def _allowed_actions(task: TaskRecord) -> list[str]:
    status = TaskStatus(task.status)
    actions = []
    if status is TaskStatus.WAITING_FOR_APPROVAL:
        if task.waiting_reason != "remote_handoff":
            actions.append("approve")
        actions.append("reject")
    if status not in (TaskStatus.SUCCEEDED, TaskStatus.CANCELLED, TaskStatus.INTEGRATING):
        actions.append("cancel")
    return actions
