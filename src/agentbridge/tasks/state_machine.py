"""Explicit task state machine. Invalid transitions are rejected."""

from __future__ import annotations

from agentbridge.errors import InvalidTransitionError
from agentbridge.tasks.models import TaskStatus

S = TaskStatus

TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    S.PENDING: frozenset({S.READY, S.CANCELLED, S.FAILED}),
    S.READY: frozenset({S.QUEUED, S.CANCELLED, S.FAILED}),
    S.QUEUED: frozenset({S.RUNNING, S.CANCELLED, S.INTERRUPTED, S.FAILED}),
    S.RUNNING: frozenset(
        {
            S.VALIDATING,
            S.WAITING_FOR_APPROVAL,  # remote handoff prepared; waiting for a human
            S.QUEUED,  # retry after a retryable failure
            S.FAILED,
            S.CANCELLED,
            S.INTERRUPTED,
        }
    ),
    S.VALIDATING: frozenset(
        {S.WAITING_FOR_APPROVAL, S.SUCCEEDED, S.FAILED, S.CANCELLED, S.INTERRUPTED}
    ),
    S.WAITING_FOR_APPROVAL: frozenset(
        {
            S.INTEGRATING,  # approved
            S.VALIDATING,  # remote result imported, or re-validation requested
            S.SUCCEEDED,  # approved without anything to merge
            S.CANCELLED,  # rejected
            S.FAILED,
        }
    ),
    S.INTEGRATING: frozenset({S.SUCCEEDED, S.FAILED, S.WAITING_FOR_APPROVAL, S.INTERRUPTED}),
    S.INTERRUPTED: frozenset({S.QUEUED, S.VALIDATING, S.CANCELLED, S.FAILED}),
    S.FAILED: frozenset({S.QUEUED}),  # explicit, user-requested retry only
    S.SUCCEEDED: frozenset(),
    S.CANCELLED: frozenset(),
}


def can_transition(current: TaskStatus, target: TaskStatus) -> bool:
    return target in TRANSITIONS[current]


def ensure_transition(current: TaskStatus, target: TaskStatus) -> None:
    if not can_transition(current, target):
        allowed = ", ".join(sorted(s.value for s in TRANSITIONS[current])) or "none (terminal)"
        raise InvalidTransitionError(
            f"Invalid task state transition {current.value} -> {target.value}",
            hint=f"Allowed from {current.value}: {allowed}",
        )
