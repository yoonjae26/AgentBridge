"""SQLite database setup (SQLAlchemy 2.x, WAL mode)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Engine,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
    select,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

SCHEMA_VERSION = 1


def utcnow() -> str:
    """Timestamps are stored as ISO-8601 UTC strings (SQLite has no tz-aware type)."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def parse_ts(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[str]: JSON}


class Meta(Base):
    __tablename__ = "meta"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(256))


class RunRecord(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(128))
    objective: Mapped[str] = mapped_column(Text)
    planner: Mapped[str] = mapped_column(String(64))
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    warnings: Mapped[list[str]] = mapped_column(JSON, default=list)
    policy: Mapped[str] = mapped_column(String(16))
    base_branch: Mapped[str | None] = mapped_column(String(256), nullable=True)
    base_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=utcnow)


class TaskRecord(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    project_id: Mapped[str] = mapped_column(String(128))
    key: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    assigned_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    routing_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    dependencies: Mapped[list[str]] = mapped_column(JSON, default=list)
    acceptance_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    expected_files: Mapped[list[str]] = mapped_column(JSON, default=list)
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), default=utcnow)
    updated_at: Mapped[str] = mapped_column(String(40), default=utcnow)
    started_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    heartbeat_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    execution_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workspace_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    git_branch: Mapped[str | None] = mapped_column(String(256), nullable=True)
    base_branch: Mapped[str | None] = mapped_column(String(256), nullable=True)
    base_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    head_commit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    changed_files: Mapped[list[str]] = mapped_column(JSON, default=list)
    validation_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    waiting_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class EventRecord(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    type: Mapped[str] = mapped_column(String(64))
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=utcnow)


class ExecutionRecord(Base):
    __tablename__ = "executions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    provider: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[str] = mapped_column(String(40), default=utcnow)
    finished_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ValidationRecord(Base):
    __tablename__ = "validations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    outcome: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[str] = mapped_column(String(40), default=utcnow)


def _configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=10000")
    cursor.close()


class Database:
    """Owns the engine and session factory for one project database."""

    def __init__(self, path: Path | str) -> None:
        if str(path) == ":memory:":
            url = "sqlite://"
        else:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite:///{Path(path).as_posix()}"
        self.engine: Engine = create_engine(
            url, connect_args={"check_same_thread": False, "timeout": 30}
        )
        event.listen(self.engine, "connect", _configure_sqlite)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)
        self._migrate()

    def _migrate(self) -> None:
        # Schema is created from metadata. A versioned migration tool (Alembic) is
        # planned; the stored schema version lets us detect incompatible databases.
        Base.metadata.create_all(self.engine)
        with self.session() as session, session.begin():
            row = session.get(Meta, "schema_version")
            if row is None:
                session.add(Meta(key="schema_version", value=str(SCHEMA_VERSION)))
            elif int(row.value) > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {row.value} is newer than this AgentBridge "
                    f"release supports ({SCHEMA_VERSION}). Upgrade AgentBridge."
                )

    def session(self) -> Session:
        return self._sessions()

    def schema_version(self) -> int:
        with self.session() as session:
            value = session.scalar(select(Meta.value).where(Meta.key == "schema_version"))
            return int(value or 0)

    def close(self) -> None:
        self.engine.dispose()
