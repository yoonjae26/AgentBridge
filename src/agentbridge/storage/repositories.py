"""Data-access layer. All state changes go through here."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select, update

from agentbridge.errors import InvalidTransitionError, NotFoundError
from agentbridge.security.secrets import redact
from agentbridge.storage.database import (
    Database,
    EventRecord,
    ExecutionRecord,
    RunRecord,
    TaskRecord,
    ValidationRecord,
    utcnow,
)
from agentbridge.tasks.models import TERMINAL_STATUSES, TaskStatus
from agentbridge.tasks.state_machine import ensure_transition


class Store:
    def __init__(self, db: Database) -> None:
        self.db = db

    # ----------------------------------------------------------------- runs
    def add_run(self, run: RunRecord) -> RunRecord:
        with self.db.session() as session, session.begin():
            session.add(run)
        return run

    def get_run(self, run_id: str) -> RunRecord:
        with self.db.session() as session:
            run = session.get(RunRecord, run_id)
        if run is None:
            raise NotFoundError(f"Run not found: {run_id}")
        return run

    # ---------------------------------------------------------------- tasks
    def add_task(self, task: TaskRecord) -> TaskRecord:
        with self.db.session() as session, session.begin():
            session.add(task)
            session.add(
                EventRecord(
                    run_id=task.run_id,
                    task_id=task.id,
                    type="task.created",
                    to_status=task.status,
                    message=f"Task created: {task.title}",
                )
            )
        return task

    def get_task(self, task_id: str) -> TaskRecord:
        with self.db.session() as session:
            task = session.get(TaskRecord, task_id)
        if task is None:
            raise NotFoundError(f"Task not found: {task_id}")
        return task

    def find_task(self, ref: str) -> TaskRecord:
        """Resolve a full id or unique prefix."""
        with self.db.session() as session:
            exact = session.get(TaskRecord, ref)
            if exact is not None:
                return exact
            matches = list(
                session.scalars(select(TaskRecord).where(TaskRecord.id.startswith(ref)).limit(3))
            )
        if not matches:
            raise NotFoundError(
                f"Task not found: {ref}", hint="Run 'agentbridge tasks list' to see task ids."
            )
        if len(matches) > 1:
            raise NotFoundError(f"Task id prefix {ref!r} is ambiguous; use more characters")
        return matches[0]

    def list_tasks(
        self,
        run_id: str | None = None,
        statuses: Iterable[TaskStatus] | None = None,
        limit: int | None = None,
    ) -> list[TaskRecord]:
        query = select(TaskRecord).order_by(TaskRecord.created_at.desc(), TaskRecord.id)
        if run_id:
            query = (
                query.where(TaskRecord.run_id == run_id)
                .order_by(None)
                .order_by(TaskRecord.created_at, TaskRecord.id)
            )
        if statuses is not None:
            query = query.where(TaskRecord.status.in_([s.value for s in statuses]))
        if limit:
            query = query.limit(limit)
        with self.db.session() as session:
            return list(session.scalars(query))

    def update_task(self, task_id: str, **fields: Any) -> TaskRecord:
        for key in ("result_summary", "error_message"):
            if isinstance(fields.get(key), str):
                fields[key] = redact(fields[key])
        fields["updated_at"] = utcnow()
        with self.db.session() as session, session.begin():
            task = session.get(TaskRecord, task_id)
            if task is None:
                raise NotFoundError(f"Task not found: {task_id}")
            for key, value in fields.items():
                if not hasattr(task, key):
                    raise AttributeError(key)
                setattr(task, key, value)
        return task

    def transition(
        self,
        task_id: str,
        target: TaskStatus,
        message: str = "",
        data: dict[str, Any] | None = None,
        **fields: Any,
    ) -> TaskRecord:
        """Atomically move a task to ``target`` and record the transition event.

        Uses compare-and-swap on the current status so two processes cannot both
        make the same transition.
        """
        current_task = self.get_task(task_id)
        current = TaskStatus(current_task.status)
        ensure_transition(current, target)
        now = utcnow()
        values: dict[str, Any] = {"status": target.value, "updated_at": now, **fields}
        if target is TaskStatus.RUNNING and current_task.started_at is None:
            values["started_at"] = now
        if target in TERMINAL_STATUSES or target is TaskStatus.FAILED:
            values["completed_at"] = now
        for key in ("result_summary", "error_message"):
            if isinstance(values.get(key), str):
                values[key] = redact(values[key])
        with self.db.session() as session, session.begin():
            result = session.execute(
                update(TaskRecord)
                .where(TaskRecord.id == task_id, TaskRecord.status == current.value)
                .values(**values)
            )
            if result.rowcount != 1:  # type: ignore[attr-defined]
                raise InvalidTransitionError(
                    f"Task {task_id} changed state concurrently; transition to "
                    f"{target.value} aborted"
                )
            session.add(
                EventRecord(
                    run_id=current_task.run_id,
                    task_id=task_id,
                    type="task.transition",
                    from_status=current.value,
                    to_status=target.value,
                    message=redact(message),
                    data=data or {},
                )
            )
        return self.get_task(task_id)

    # --------------------------------------------------------------- events
    def add_event(
        self,
        type_: str,
        message: str = "",
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        with self.db.session() as session, session.begin():
            session.add(
                EventRecord(
                    run_id=run_id,
                    task_id=task_id,
                    type=type_,
                    message=redact(message),
                    data=data or {},
                )
            )

    def list_events(
        self, task_id: str | None = None, run_id: str | None = None
    ) -> list[EventRecord]:
        query = select(EventRecord).order_by(EventRecord.id)
        if task_id:
            query = query.where(EventRecord.task_id == task_id)
        if run_id:
            query = query.where(EventRecord.run_id == run_id)
        with self.db.session() as session:
            return list(session.scalars(query))

    # ----------------------------------------------------------- executions
    def add_execution(self, record: ExecutionRecord) -> ExecutionRecord:
        with self.db.session() as session, session.begin():
            session.add(record)
        return record

    def update_execution(self, execution_id: str, **fields: Any) -> None:
        for key in ("summary", "error"):
            if isinstance(fields.get(key), str):
                fields[key] = redact(fields[key])
        with self.db.session() as session, session.begin():
            record = session.get(ExecutionRecord, execution_id)
            if record is None:
                raise NotFoundError(f"Execution not found: {execution_id}")
            for key, value in fields.items():
                setattr(record, key, value)

    def list_executions(self, task_id: str) -> list[ExecutionRecord]:
        with self.db.session() as session:
            return list(
                session.scalars(
                    select(ExecutionRecord)
                    .where(ExecutionRecord.task_id == task_id)
                    .order_by(ExecutionRecord.attempt)
                )
            )

    # ----------------------------------------------------------- validation
    def add_validation(self, task_id: str, outcome: str, data: dict[str, Any]) -> None:
        with self.db.session() as session, session.begin():
            session.add(ValidationRecord(task_id=task_id, outcome=outcome, data=data))

    def list_validations(self, task_id: str) -> list[ValidationRecord]:
        with self.db.session() as session:
            return list(
                session.scalars(
                    select(ValidationRecord)
                    .where(ValidationRecord.task_id == task_id)
                    .order_by(ValidationRecord.id)
                )
            )
