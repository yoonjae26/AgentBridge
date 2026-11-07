"""Event recording: database audit trail + per-task log file + live callback."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentbridge.security.secrets import redact
from agentbridge.storage.database import utcnow
from agentbridge.storage.repositories import Store

EventCallback = Callable[[str, str, str | None], None]  # (type, message, task_id)


class EventRecorder:
    def __init__(self, store: Store, logs_dir: Path, callback: EventCallback | None = None):
        self.store = store
        self.logs_dir = logs_dir
        self.callback = callback

    def log_line(self, task_id: str | None, message: str) -> None:
        if task_id is None:
            return
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        with (self.logs_dir / f"{task_id}.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{utcnow()} {redact(message)}\n")

    def emit(
        self,
        type_: str,
        message: str,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        data: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> None:
        if persist:
            self.store.add_event(type_, message, task_id=task_id, run_id=run_id, data=data)
        self.log_line(task_id, f"[{type_}] {message}")
        if self.callback is not None:
            self.callback(type_, redact(message), task_id)

    def transitioned(self, task_id: str, status: str, message: str) -> None:
        """Transitions are persisted by Store.transition; only log and notify here."""
        self.log_line(task_id, f"[state] -> {status}: {message}")
        if self.callback is not None:
            self.callback("task.transition", f"{status}: {redact(message)}", task_id)
