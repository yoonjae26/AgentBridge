"""Startup recovery of tasks left in an active state by a dead process.

A task is considered orphaned when it is in an active state but its heartbeat
is older than ``stale_after_seconds``. If the provider can report execution
status we ask it; otherwise the outcome is uncertain and the task is marked
INTERRUPTED. Nothing is re-executed automatically.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from agentbridge.agents.base import ExecutionState
from agentbridge.agents.capabilities import OperationSupport
from agentbridge.errors import AgentBridgeError
from agentbridge.storage.database import parse_ts
from agentbridge.storage.repositories import Store
from agentbridge.tasks.models import ACTIVE_STATUSES, TaskStatus

if TYPE_CHECKING:
    from agentbridge.agents.registry import AgentRegistry
    from agentbridge.core.events import EventRecorder


def _is_stale(last_seen: str | None, stale_after: float, now: datetime) -> bool:
    ts = parse_ts(last_seen)
    return ts is None or now - ts > timedelta(seconds=stale_after)


def _provider_still_running(registry: AgentRegistry, provider: str | None, exec_id: str) -> bool:
    if not provider or provider not in registry.names():
        return False
    adapter = registry.get(provider, require_enabled=False)
    try:
        caps = asyncio.run(adapter.get_capabilities()) if not _loop_running() else None
        if caps is None or caps.status_query is not OperationSupport.SUPPORTED:
            return False
        state = asyncio.run(adapter.get_status(exec_id))
    except (AgentBridgeError, RuntimeError):
        return False
    return state is ExecutionState.RUNNING


def _loop_running() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def recover_stale_tasks(
    store: Store,
    registry: AgentRegistry,
    stale_after_seconds: float,
    events: EventRecorder | None = None,
    *,
    only: Iterable[str] | None = None,
    mark: bool = True,
) -> list[str]:
    """Return ids of stale active tasks; mark them INTERRUPTED when ``mark``."""
    now = datetime.now(UTC)
    wanted = set(only) if only is not None else None
    stale: list[str] = []
    for task in store.list_tasks(statuses=ACTIVE_STATUSES):
        if wanted is not None and task.id not in wanted:
            continue
        last_seen = task.heartbeat_at or task.updated_at
        if not _is_stale(last_seen, stale_after_seconds, now):
            continue
        if task.execution_id and _provider_still_running(
            registry, task.assigned_provider, task.execution_id
        ):
            continue
        stale.append(task.id)
        if not mark:
            continue
        message = (
            f"Recovered after restart: task was {task.status} with no live process; "
            "the execution outcome is uncertain"
        )
        try:
            store.transition(task.id, TaskStatus.INTERRUPTED, message)
        except AgentBridgeError:
            continue
        if events is not None:
            events.transitioned(task.id, TaskStatus.INTERRUPTED.value, message)
    return stale
