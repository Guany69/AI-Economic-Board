"""Repositories: all DB access for the application lives here.

State transitions are enforced with a guarded UPDATE (rowcount 0 ->
InvalidStateTransitionError), so no race can produce an illegal transition.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.domain.entities import (
    EconomicChange,
    LLMInterpretation,
    MetricDelta,
    MetricResult,
    TaxCalculatorResult,
    TaxFairAdapterResult,
)
from app.domain.enums import ChangeType, ModelName, ModelRoute, RunStatus
from app.domain.errors import BaselineNotFoundError, InvalidStateTransitionError
from app.domain.state import ALLOWED_TRANSITIONS
from app.infrastructure.persistence.models import (
    BaselineMetricRow,
    BaselineRow,
    EconomicChangeRow,
    LLMInterpretationRow,
    MetricDeltaRow,
    ModelArtifactRow,
    ModelVersionRow,
    SimulationMetricRow,
    SimulationModelVersionRow,
    SimulationRunRow,
    TaxCalculatorResultRow,
    TaxFairAdapterResultRow,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SimulationRunRepository:
    def __init__(self, session: Session):
        self.s = session

    def create(self, baseline_id: int, change: EconomicChange, route: ModelRoute,
               horizon_quarters: int) -> uuid.UUID:
        run = SimulationRunRow(status=RunStatus.PENDING.value, baseline_id=baseline_id,
                               horizon_quarters=horizon_quarters)
        self.s.add(run)
        self.s.flush()
        self.s.add(EconomicChangeRow(
            run_id=run.id,
            variable_id=change.variable_id,
            model_route=route.value,
            change_type=change.change_type.value,
            change_value=change.change_value,
        ))
        return run.id

    def get(self, run_id: uuid.UUID) -> SimulationRunRow | None:
        return self.s.get(SimulationRunRow, run_id)

    def get_change(self, run_id: uuid.UUID) -> EconomicChangeRow | None:
        return self.s.scalar(select(EconomicChangeRow).where(EconomicChangeRow.run_id == run_id))

    def transition(self, run_id: uuid.UUID, from_status: RunStatus, to_status: RunStatus,
                   error_type: str | None = None, error_message: str | None = None) -> None:
        if to_status not in ALLOWED_TRANSITIONS[from_status]:
            raise InvalidStateTransitionError(from_status, to_status)
        values: dict = {"status": to_status.value}
        if to_status is RunStatus.RUNNING:
            values["started_at"] = _utcnow()
        if to_status in (RunStatus.COMPLETED, RunStatus.FAILED):
            values["finished_at"] = _utcnow()
        if error_type is not None:
            values["error_type"] = error_type
            values["error_message"] = (error_message or "")[:8000]
        result = self.s.execute(
            update(SimulationRunRow)
            .where(SimulationRunRow.id == run_id,
                   SimulationRunRow.status == from_status.value)
            .values(**values)
        )
        if result.rowcount != 1:
            raise InvalidStateTransitionError(f"{from_status} (stale)", to_status)

    def fail_from_any_active(self, run_id: uuid.UUID, error_type: str, error_message: str) -> None:
        """Force FAILED from PENDING or RUNNING (used by the failure handler)."""
        self.s.execute(
            update(SimulationRunRow)
            .where(SimulationRunRow.id == run_id,
                   SimulationRunRow.status.in_([RunStatus.PENDING.value, RunStatus.RUNNING.value]))
            .values(status=RunStatus.FAILED.value, error_type=error_type,
                    error_message=error_message[:8000], finished_at=_utcnow())
        )

    def find_by_status(self, status: RunStatus) -> list[SimulationRunRow]:
        return list(self.s.scalars(
            select(SimulationRunRow).where(SimulationRunRow.status == status.value)
            .order_by(SimulationRunRow.created_at)
        ))


class ModelVersionRepository:
    def __init__(self, session: Session):
        self.s = session

    def get_or_create(self, model_name: ModelName, version_label: str, details: dict) -> int:
        row = self.s.scalar(
            select(ModelVersionRow).where(
                ModelVersionRow.model_name == model_name.value,
                ModelVersionRow.version_label == version_label,
            )
        )
        if row is None:
            row = ModelVersionRow(model_name=model_name.value, version_label=version_label,
                                  details=details)
            self.s.add(row)
            self.s.flush()
        return row.id

    def link_to_run(self, run_id: uuid.UUID, model_version_id: int) -> None:
        exists = self.s.scalar(
            select(SimulationModelVersionRow).where(
                SimulationModelVersionRow.run_id == run_id,
                SimulationModelVersionRow.model_version_id == model_version_id,
            )
        )
        if exists is None:
            self.s.add(SimulationModelVersionRow(run_id=run_id, model_version_id=model_version_id))

    def versions_for_run(self, run_id: uuid.UUID) -> list[ModelVersionRow]:
        return list(self.s.scalars(
            select(ModelVersionRow)
            .join(SimulationModelVersionRow,
                  SimulationModelVersionRow.model_version_id == ModelVersionRow.id)
            .where(SimulationModelVersionRow.run_id == run_id)
        ))


class ArtifactRepository:
    def __init__(self, session: Session):
        self.s = session

    def register(self, model_version_id: int, name: str, path: str, sha256: str,
                 size_bytes: int) -> int:
        row = ModelArtifactRow(model_version_id=model_version_id, name=name, path=path,
                               sha256=sha256, size_bytes=size_bytes)
        self.s.add(row)
        self.s.flush()
        return row.id

    def get(self, artifact_id: int) -> ModelArtifactRow | None:
        return self.s.get(ModelArtifactRow, artifact_id)


class BaselineRepository:
    def __init__(self, session: Session):
        self.s = session

    def create(self, name: str, fair_model_version_id: int, solve_start: str, solve_end: str,
               snapshot_artifact_id: int | None) -> int:
        row = BaselineRow(name=name, status="ACTIVE",
                          fair_model_version_id=fair_model_version_id,
                          solve_start=solve_start, solve_end=solve_end,
                          snapshot_artifact_id=snapshot_artifact_id)
        self.s.add(row)
        self.s.flush()
        return row.id

    def retire_all_active(self) -> None:
        self.s.execute(update(BaselineRow).where(BaselineRow.status == "ACTIVE")
                       .values(status="RETIRED"))

    def get_active(self) -> BaselineRow:
        row = self.s.scalar(select(BaselineRow).where(BaselineRow.status == "ACTIVE")
                            .order_by(BaselineRow.id.desc()))
        if row is None:
            raise BaselineNotFoundError()
        return row

    def get(self, baseline_id: int) -> BaselineRow | None:
        return self.s.get(BaselineRow, baseline_id)

    def add_metrics(self, baseline_id: int, metrics: list[MetricResult]) -> None:
        for m in metrics:
            self.s.add(BaselineMetricRow(baseline_id=baseline_id, metric=m.metric,
                                         period=m.period, value=m.value, unit=m.unit))

    def get_metrics(self, baseline_id: int) -> list[MetricResult]:
        rows = self.s.scalars(
            select(BaselineMetricRow).where(BaselineMetricRow.baseline_id == baseline_id)
            .order_by(BaselineMetricRow.metric, BaselineMetricRow.period)
        )
        return [
            MetricResult(model=ModelName.FAIR, metric=r.metric, period=r.period,
                         value=Decimal(r.value), unit=r.unit)
            for r in rows
        ]


class MetricRepository:
    def __init__(self, session: Session):
        self.s = session

    def add_simulation_metrics(self, run_id: uuid.UUID, metrics: list[MetricResult]) -> None:
        for m in metrics:
            self.s.add(SimulationMetricRow(run_id=run_id, metric=m.metric, period=m.period,
                                           value=m.value, unit=m.unit))

    def get_simulation_metrics(self, run_id: uuid.UUID) -> list[MetricResult]:
        rows = self.s.scalars(
            select(SimulationMetricRow).where(SimulationMetricRow.run_id == run_id)
            .order_by(SimulationMetricRow.metric, SimulationMetricRow.period)
        )
        return [
            MetricResult(model=ModelName.FAIR, metric=r.metric, period=r.period,
                         value=Decimal(r.value), unit=r.unit)
            for r in rows
        ]

    def add_deltas(self, run_id: uuid.UUID, deltas: list[MetricDelta]) -> None:
        for d in deltas:
            self.s.add(MetricDeltaRow(
                run_id=run_id, metric=d.metric, period=d.period,
                baseline_value=d.baseline_value, changed_value=d.changed_value,
                absolute_delta=d.absolute_delta, percentage_delta=d.percentage_delta,
                unit=d.unit,
            ))

    def get_deltas(self, run_id: uuid.UUID) -> list[MetricDelta]:
        rows = self.s.scalars(
            select(MetricDeltaRow).where(MetricDeltaRow.run_id == run_id)
            .order_by(MetricDeltaRow.metric, MetricDeltaRow.period)
        )
        return [
            MetricDelta(
                metric=r.metric, period=r.period,
                baseline_value=Decimal(r.baseline_value),
                changed_value=Decimal(r.changed_value),
                absolute_delta=Decimal(r.absolute_delta),
                percentage_delta=Decimal(r.percentage_delta) if r.percentage_delta is not None else None,
                unit=r.unit,
            )
            for r in rows
        ]


class TaxResultRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, run_id: uuid.UUID, result: TaxCalculatorResult) -> int:
        row = TaxCalculatorResultRow(
            run_id=run_id, tax_year=result.tax_year, reform=result.reform,
            base_iitax=result.base_iitax, reform_iitax=result.reform_iitax,
            base_payrolltax=result.base_payrolltax, reform_payrolltax=result.reform_payrolltax,
            base_combined=result.base_combined, reform_combined=result.reform_combined,
            base_agi=result.base_agi, base_expanded_income=result.base_expanded_income,
            total_weight=result.total_weight, soi_iitax=result.soi_iitax,
            taxcalc_version=result.taxcalc_version,
        )
        self.s.add(row)
        self.s.flush()
        return row.id

    def get_for_run(self, run_id: uuid.UUID) -> TaxCalculatorResultRow | None:
        return self.s.scalar(select(TaxCalculatorResultRow)
                             .where(TaxCalculatorResultRow.run_id == run_id))


class AdapterResultRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, run_id: uuid.UUID, tax_result_id: int, result: TaxFairAdapterResult) -> int:
        row = TaxFairAdapterResultRow(
            run_id=run_id, tax_calculator_result_id=tax_result_id,
            mapping_id=result.mapping_id, method=result.method,
            source_variable_id=result.source_variable_id,
            target_fair_variable=result.target_fair_variable,
            fair_change_type=result.fair_change_type.value,
            derived_delta=result.derived_delta,
            quarterly_allocation_method=result.quarterly_allocation_method,
            quarterly_values=[str(v) for v in result.quarterly_values],
            conversion_metadata=result.conversion_metadata,
        )
        self.s.add(row)
        self.s.flush()
        return row.id

    def get_for_run(self, run_id: uuid.UUID) -> TaxFairAdapterResultRow | None:
        return self.s.scalar(select(TaxFairAdapterResultRow)
                             .where(TaxFairAdapterResultRow.run_id == run_id))


class InterpretationRepository:
    def __init__(self, session: Session):
        self.s = session

    def add(self, run_id: uuid.UUID, interp: LLMInterpretation) -> int:
        row = LLMInterpretationRow(
            run_id=run_id, model_id=interp.model_id, prompt_version=interp.prompt_version,
            prompt_text=interp.prompt_text, response_text=interp.response_text,
            input_tokens=interp.input_tokens, output_tokens=interp.output_tokens,
            stop_reason=interp.stop_reason,
        )
        self.s.add(row)
        self.s.flush()
        return row.id

    def get_for_run(self, run_id: uuid.UUID) -> LLMInterpretationRow | None:
        return self.s.scalar(select(LLMInterpretationRow)
                             .where(LLMInterpretationRow.run_id == run_id))
