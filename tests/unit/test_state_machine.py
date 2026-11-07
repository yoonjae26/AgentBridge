import pytest

from agentbridge.errors import InvalidTransitionError
from agentbridge.tasks.models import TaskStatus as S
from agentbridge.tasks.state_machine import TRANSITIONS, can_transition, ensure_transition


def test_every_status_has_rules():
    assert set(TRANSITIONS) == set(S)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.PENDING, S.READY),
        (S.READY, S.QUEUED),
        (S.QUEUED, S.RUNNING),
        (S.RUNNING, S.VALIDATING),
        (S.VALIDATING, S.WAITING_FOR_APPROVAL),
        (S.WAITING_FOR_APPROVAL, S.INTEGRATING),
        (S.INTEGRATING, S.SUCCEEDED),
        (S.RUNNING, S.QUEUED),
        (S.INTERRUPTED, S.VALIDATING),
        (S.FAILED, S.QUEUED),
    ],
)
def test_valid_transitions(current, target):
    assert can_transition(current, target)
    ensure_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.PENDING, S.RUNNING),
        (S.RUNNING, S.SUCCEEDED),  # success requires validation
        (S.VALIDATING, S.INTEGRATING),  # merge requires approval
        (S.SUCCEEDED, S.RUNNING),
        (S.CANCELLED, S.QUEUED),
        (S.QUEUED, S.SUCCEEDED),
    ],
)
def test_invalid_transitions_rejected(current, target):
    assert not can_transition(current, target)
    with pytest.raises(InvalidTransitionError):
        ensure_transition(current, target)


def test_terminal_states_have_no_exits():
    assert TRANSITIONS[S.SUCCEEDED] == frozenset()
    assert TRANSITIONS[S.CANCELLED] == frozenset()


def test_merge_only_through_approval():
    sources = [s for s, targets in TRANSITIONS.items() if S.INTEGRATING in targets]
    assert sources == [S.WAITING_FOR_APPROVAL]
