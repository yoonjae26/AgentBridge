from pathlib import Path

import pytest

from agentbridge.errors import InvalidTransitionError, NotFoundError
from agentbridge.storage.database import Database, RunRecord, TaskRecord
from agentbridge.storage.repositories import Store
from agentbridge.tasks.models import TaskStatus


def seed(store: Store, task_id: str = "r1-task-001") -> None:
    store.add_run(
        RunRecord(id="r1", project_id="p", objective="o", planner="single", policy="standard")
    )
    store.add_task(
        TaskRecord(
            id=task_id,
            run_id="r1",
            project_id="p",
            key="task-001",
            title="t",
            role="developer",
            status="PENDING",
        )
    )


def test_crud_and_events(tmp_path: Path):
    store = Store(Database(tmp_path / "db.sqlite"))
    seed(store)
    task = store.transition("r1-task-001", TaskStatus.READY, "deps ok")
    assert task.status == "READY"
    events = store.list_events(task_id="r1-task-001")
    assert [e.type for e in events] == ["task.created", "task.transition"]
    assert events[1].from_status == "PENDING" and events[1].to_status == "READY"


def test_invalid_transition_is_rejected_and_not_recorded(tmp_path: Path):
    store = Store(Database(tmp_path / "db.sqlite"))
    seed(store)
    with pytest.raises(InvalidTransitionError):
        store.transition("r1-task-001", TaskStatus.SUCCEEDED)
    assert store.get_task("r1-task-001").status == "PENDING"
    assert len(store.list_events(task_id="r1-task-001")) == 1


def test_state_persists_across_restart(tmp_path: Path):
    path = tmp_path / "db.sqlite"
    db = Database(path)
    store = Store(db)
    seed(store)
    store.transition("r1-task-001", TaskStatus.READY)
    store.update_task("r1-task-001", result_summary="hello", retry_count=2)
    db.close()
    reopened = Store(Database(path))
    task = reopened.get_task("r1-task-001")
    assert (task.status, task.result_summary, task.retry_count) == ("READY", "hello", 2)


def test_wal_mode_enabled(tmp_path: Path):
    db = Database(tmp_path / "db.sqlite")
    with db.engine.connect() as conn:
        mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
    assert str(mode).lower() == "wal"


def test_find_task_by_prefix(tmp_path: Path):
    store = Store(Database(tmp_path / "db.sqlite"))
    seed(store)
    assert store.find_task("r1-task").id == "r1-task-001"
    with pytest.raises(NotFoundError):
        store.find_task("zzz")


def test_secrets_redacted_on_write(tmp_path: Path):
    store = Store(Database(tmp_path / "db.sqlite"))
    seed(store)
    store.update_task(
        "r1-task-001", error_message="failed with key sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUV"
    )
    assert "sk-ant" not in (store.get_task("r1-task-001").error_message or "")


def test_alembic_fresh_and_legacy_databases(tmp_path: Path):
    from sqlalchemy import create_engine, text

    from agentbridge.storage.database import Base

    fresh = Database(tmp_path / "fresh.db")
    with fresh.engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001"
    fresh.close()

    # A database created by v0.1.0 (metadata.create_all, no alembic_version table).
    legacy_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{legacy_path.as_posix()}")
    Base.metadata.create_all(engine)
    engine.dispose()
    legacy = Database(legacy_path)
    seed(Store(legacy))  # schema usable, data writable
    with legacy.engine.connect() as conn:
        assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar() == "0001"
    legacy.close()


def test_newer_schema_revision_is_refused(tmp_path: Path):
    from sqlalchemy import text

    path = tmp_path / "db.sqlite"
    Database(path).close()
    db = Database(path)
    with db.engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = '9999'"))
    db.close()
    with pytest.raises(RuntimeError, match="newer"):
        Database(path)
