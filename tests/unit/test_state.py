import pytest

from app.domain.enums import RunStatus
from app.domain.errors import InvalidStateTransitionError
from app.domain.state import ALLOWED_TRANSITIONS, assert_transition


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (RunStatus.PENDING, RunStatus.RUNNING),
        (RunStatus.PENDING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.COMPLETED),
        (RunStatus.RUNNING, RunStatus.FAILED),
    ],
)
def test_allowed_transitions(from_status, to_status):
    assert_transition(from_status, to_status)  # no raise


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (RunStatus.PENDING, RunStatus.COMPLETED),   # must pass through RUNNING
        (RunStatus.COMPLETED, RunStatus.RUNNING),
        (RunStatus.COMPLETED, RunStatus.FAILED),
        (RunStatus.FAILED, RunStatus.RUNNING),
        (RunStatus.FAILED, RunStatus.PENDING),
        (RunStatus.RUNNING, RunStatus.PENDING),
        (RunStatus.RUNNING, RunStatus.RUNNING),
    ],
)
def test_forbidden_transitions(from_status, to_status):
    with pytest.raises(InvalidStateTransitionError):
        assert_transition(from_status, to_status)


def test_terminal_states_have_no_exits():
    assert ALLOWED_TRANSITIONS[RunStatus.COMPLETED] == frozenset()
    assert ALLOWED_TRANSITIONS[RunStatus.FAILED] == frozenset()


def test_every_status_has_a_policy():
    assert set(ALLOWED_TRANSITIONS) == set(RunStatus)
