"""Alembic environment. Migrations run programmatically from Database._migrate."""

from alembic import context

from agentbridge.storage.database import Base

connection = context.config.attributes.get("connection")
if connection is None:  # pragma: no cover - only used by `alembic` CLI during development
    from sqlalchemy import create_engine

    url = context.config.get_main_option("sqlalchemy.url") or "sqlite:///dev.db"
    connection = create_engine(url).connect()

context.configure(
    connection=connection,
    target_metadata=Base.metadata,
    render_as_batch=True,  # SQLite needs batch mode for ALTER TABLE
)
with context.begin_transaction():
    context.run_migrations()
