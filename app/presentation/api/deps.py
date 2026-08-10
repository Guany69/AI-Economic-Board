"""API dependency wiring: one AppContext + worker per process, created in
the lifespan handler."""

from dataclasses import dataclass

from app.application.context import AppContext
from app.application.orchestrator import SimulationOrchestrator
from app.application.worker import SimulationWorker


@dataclass
class ApiState:
    ctx: AppContext
    orchestrator: SimulationOrchestrator
    worker: SimulationWorker


_state: ApiState | None = None


def set_state(state: ApiState) -> None:
    global _state
    _state = state


def get_state() -> ApiState:
    assert _state is not None, "API state not initialized (lifespan did not run)"
    return _state
