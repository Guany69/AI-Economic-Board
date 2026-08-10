"""Worker tests: FIFO execution and startup orphan recovery."""

import time
from decimal import Decimal

import pytest

from app.application.context import AppContext
from app.application.orchestrator import SimulationOrchestrator
from app.application.worker import SimulationWorker
from app.business.comparison import MetricComparisonService
from app.business.routing import ChangeRouter
from app.business.validation import ChangeValidator
from app.config.loader import get_variable_registry
from app.config.settings import get_settings
from app.domain.entities import EconomicChange
from app.domain.enums import ChangeType, ModelName, ModelRoute, RunStatus
from app.infrastructure.adapters.tax_to_fair import ConfiguredTaxToFairAdapter
from app.infrastructure.persistence.repositories import (
    ArtifactRepository,
    BaselineRepository,
    ModelVersionRepository,
    SimulationRunRepository,
)
from tests.fakes import FakeFairRunner, FakeInterpreter, FakeTaxRunner, make_metrics


@pytest.fixture()
def ctx(session_factory):
    registry = get_variable_registry()
    return AppContext(
        settings=get_settings(), registry=registry,
        validator=ChangeValidator(registry), router=ChangeRouter(registry),
        comparison=MetricComparisonService(), fair_runner=FakeFairRunner(),
        tax_runner=FakeTaxRunner(), tax_adapter=ConfiguredTaxToFairAdapter(),
        interpreter=FakeInterpreter(), session_factory=session_factory,
    )


@pytest.fixture()
def seeded_baseline(session_factory, tmp_path):
    snap = tmp_path / "BASE.BIN"
    snap.write_bytes(b"fake")
    with session_factory() as s:
        fair_id = ModelVersionRepository(s).get_or_create(ModelName.FAIR, "fake-fair", {})
        art_id = ArtifactRepository(s).register(fair_id, "BASE.BIN", str(snap), "0" * 64, 4)
        bl = BaselineRepository(s)
        bid = bl.create("fake-baseline", fair_id, "2026Q3", "2029Q4", art_id)
        bl.add_metrics(bid, make_metrics())
        s.commit()
    return bid


def _wait_status(session_factory, run_id, statuses, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with session_factory() as s:
            row = SimulationRunRepository(s).get(run_id)
            if row.status in statuses:
                return row.status
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never reached {statuses}")


def test_worker_executes_enqueued_runs_fifo(ctx, seeded_baseline):
    orch = SimulationOrchestrator(ctx)
    worker = SimulationWorker(orch)
    worker.start()
    try:
        ids = [orch.submit("COG", "ABSOLUTE", 25).run_id for _ in range(3)]
        for rid in ids:
            worker.enqueue(rid)
        for rid in ids:
            assert _wait_status(ctx.session_factory, rid, {"COMPLETED"}) == "COMPLETED"
    finally:
        worker.stop()


def test_orphan_recovery(ctx, seeded_baseline):
    """RUNNING runs found at startup -> FAILED; PENDING -> re-enqueued."""
    orch = SimulationOrchestrator(ctx)
    # simulate a crash: one RUNNING, one PENDING left behind
    interrupted = orch.submit("COG", "ABSOLUTE", 25).run_id
    pending = orch.submit("COG", "ABSOLUTE", 10).run_id
    with ctx.session_factory() as s:
        SimulationRunRepository(s).transition(interrupted, RunStatus.PENDING, RunStatus.RUNNING)
        s.commit()

    worker = SimulationWorker(orch)
    worker.recover_orphans()
    worker.start()
    try:
        with ctx.session_factory() as s:
            row = SimulationRunRepository(s).get(interrupted)
            assert row.status == "FAILED"
            assert row.error_type == "InterruptedError"
        assert _wait_status(ctx.session_factory, pending, {"COMPLETED"}) == "COMPLETED"
    finally:
        worker.stop()
