import uuid
from decimal import Decimal

import pytest

from app.domain.entities import EconomicChange, MetricDelta, MetricResult
from app.domain.enums import ChangeType, ModelName, ModelRoute, RunStatus
from app.domain.errors import BaselineNotFoundError, InvalidStateTransitionError
from app.infrastructure.persistence.repositories import (
    ArtifactRepository,
    BaselineRepository,
    MetricRepository,
    ModelVersionRepository,
    SimulationRunRepository,
)


def _seed_baseline(session) -> int:
    mv = ModelVersionRepository(session)
    fair_id = mv.get_or_create(ModelName.FAIR, "test-fair-v1", {"src": "test"})
    art = ArtifactRepository(session)
    art_id = art.register(fair_id, "BASE.BIN", "/tmp/BASE.BIN", "ab" * 32, 123)
    bl = BaselineRepository(session)
    bid = bl.create("test-baseline", fair_id, "2026Q3", "2029Q4", art_id)
    bl.add_metrics(bid, [
        MetricResult(model=ModelName.FAIR, metric="GDP", period="2026Q3",
                     value=Decimal("6584.05"), unit="billions of dollars"),
    ])
    session.commit()
    return bid


def test_baseline_roundtrip(db_session):
    bid = _seed_baseline(db_session)
    bl = BaselineRepository(db_session)
    active = bl.get_active()
    assert active.id == bid
    metrics = bl.get_metrics(bid)
    assert metrics[0].value == Decimal("6584.05")
    assert metrics[0].period == "2026Q3"


def test_no_active_baseline_raises(db_session):
    with pytest.raises(BaselineNotFoundError):
        BaselineRepository(db_session).get_active()


def test_retire_active(db_session):
    _seed_baseline(db_session)
    bl = BaselineRepository(db_session)
    bl.retire_all_active()
    db_session.commit()
    with pytest.raises(BaselineNotFoundError):
        bl.get_active()


def test_run_lifecycle_and_guarded_transition(db_session):
    bid = _seed_baseline(db_session)
    runs = SimulationRunRepository(db_session)
    change = EconomicChange("COG", ChangeType.ABSOLUTE, Decimal("25"))
    run_id = runs.create(bid, change, ModelRoute.DIRECT_FAIR, 14)
    db_session.commit()

    row = runs.get(run_id)
    assert row.status == "PENDING"
    assert runs.get_change(run_id).variable_id == "COG"

    runs.transition(run_id, RunStatus.PENDING, RunStatus.RUNNING)
    db_session.commit()
    assert runs.get(run_id).started_at is not None

    # illegal by policy
    with pytest.raises(InvalidStateTransitionError):
        runs.transition(run_id, RunStatus.RUNNING, RunStatus.PENDING)

    # stale guard: claims PENDING but the row is RUNNING -> rowcount 0
    with pytest.raises(InvalidStateTransitionError):
        runs.transition(run_id, RunStatus.PENDING, RunStatus.RUNNING)
    db_session.rollback()

    runs.transition(run_id, RunStatus.RUNNING, RunStatus.COMPLETED)
    db_session.commit()
    assert runs.get(run_id).status == "COMPLETED"
    assert runs.get(run_id).finished_at is not None


def test_fail_from_any_active(db_session):
    bid = _seed_baseline(db_session)
    runs = SimulationRunRepository(db_session)
    run_id = runs.create(bid, EconomicChange("COG", ChangeType.ABSOLUTE, Decimal("1")),
                         ModelRoute.DIRECT_FAIR, 14)
    db_session.commit()
    runs.fail_from_any_active(run_id, "FairExecutionError", "boom")
    db_session.commit()
    row = runs.get(run_id)
    assert row.status == "FAILED"
    assert row.error_type == "FairExecutionError"


def test_metric_deltas_roundtrip_preserves_decimals_and_null_pct(db_session):
    bid = _seed_baseline(db_session)
    runs = SimulationRunRepository(db_session)
    run_id = runs.create(bid, EconomicChange("COG", ChangeType.ABSOLUTE, Decimal("25")),
                         ModelRoute.DIRECT_FAIR, 14)
    metrics = MetricRepository(db_session)
    metrics.add_deltas(run_id, [
        MetricDelta("GDP", "2026Q3", Decimal("6584.05"), Decimal("6614.572"),
                    Decimal("30.522"), Decimal("0.0046357"), "billions of dollars"),
        MetricDelta("SGP", "2026Q3", Decimal("0"), Decimal("-5.5"),
                    Decimal("-5.5"), None, "billions of dollars"),
    ])
    db_session.commit()
    out = metrics.get_deltas(run_id)
    assert out[0].absolute_delta == Decimal("30.522")
    assert out[1].percentage_delta is None
