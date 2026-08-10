"""Single background worker: strict FIFO execution of simulation runs.

One daemon thread + queue.Queue. Model runs are memory-heavy (Tax-Calculator
holds ~1.5 GB for a baseline+reform pair), so strictly sequential execution
is a deliberate MVP guarantee.
"""

import logging
import queue
import threading
from uuid import UUID

from app.application.orchestrator import SimulationOrchestrator
from app.domain.enums import RunStatus
from app.infrastructure.persistence.repositories import SimulationRunRepository

logger = logging.getLogger(__name__)

_SENTINEL = object()


class SimulationWorker:
    def __init__(self, orchestrator: SimulationOrchestrator):
        self.orchestrator = orchestrator
        self._queue: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="simulation-worker",
                                        daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if self._thread is None:
            return
        self._queue.put(_SENTINEL)
        self._thread.join(timeout=timeout)
        self._thread = None

    def enqueue(self, run_id: UUID) -> None:
        self._queue.put(run_id)

    def recover_orphans(self) -> None:
        """Startup recovery: RUNNING runs were interrupted -> FAILED;
        PENDING runs are re-enqueued in creation order."""
        with self.orchestrator.ctx.session_factory() as session:
            runs = SimulationRunRepository(session)
            for row in runs.find_by_status(RunStatus.RUNNING):
                runs.fail_from_any_active(
                    row.id, "InterruptedError",
                    "Run was interrupted by a service restart",
                )
                logger.warning("Recovered orphaned RUNNING run %s -> FAILED", row.id)
            pending = runs.find_by_status(RunStatus.PENDING)
            session.commit()
        for row in pending:
            logger.info("Re-enqueueing PENDING run %s", row.id)
            self.enqueue(row.id)

    def _loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                return
            try:
                self.orchestrator.execute(item)
            except Exception:  # pragma: no cover — execute() never raises
                logger.exception("Unexpected worker error for run %s", item)
            finally:
                self._queue.task_done()
