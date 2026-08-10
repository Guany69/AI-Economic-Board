"""Simulation run state machine: PENDING -> RUNNING -> COMPLETED | FAILED."""

from app.domain.enums import RunStatus
from app.domain.errors import InvalidStateTransitionError

ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset({RunStatus.COMPLETED, RunStatus.FAILED}),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
}


def assert_transition(from_status: RunStatus, to_status: RunStatus) -> None:
    if to_status not in ALLOWED_TRANSITIONS[from_status]:
        raise InvalidStateTransitionError(from_status, to_status)
