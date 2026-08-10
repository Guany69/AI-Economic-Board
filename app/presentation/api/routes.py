"""API routes."""

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.domain.enums import ModelRoute
from app.domain.errors import BaselineNotFoundError, DomainError, ValidationError
from app.infrastructure.persistence.repositories import (
    AdapterResultRepository,
    BaselineRepository,
    InterpretationRepository,
    MetricRepository,
    ModelVersionRepository,
    SimulationRunRepository,
    TaxResultRepository,
)
from app.presentation.api import schemas
from app.presentation.api.deps import get_state

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/variables", response_model=list[schemas.VariableOut])
def list_variables():
    state = get_state()
    return [
        schemas.VariableOut(
            id=v.id, label=v.label,
            model="FAIR" if v.model_route is ModelRoute.DIRECT_FAIR else "TAX_CALCULATOR",
            unit=v.unit,
            allowed_change_types=sorted(t.value for t in v.allowed_change_types),
            description=v.description,
        )
        for v in state.ctx.registry.all()
    ]


@router.post("/simulations", response_model=schemas.SubmissionResponse, status_code=202)
def submit_simulation(req: schemas.SimulationRequest):
    state = get_state()
    try:
        submission = state.orchestrator.submit(
            req.variable_id, req.change.type, req.change.value, req.horizon_quarters
        )
    except ValidationError as exc:                       # Case C
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except BaselineNotFoundError as exc:                 # Case D
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except DomainError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    state.worker.enqueue(submission.run_id)
    return schemas.SubmissionResponse(
        simulation_run_id=submission.run_id, status=submission.status
    )


@router.get("/simulations/{run_id}", response_model=schemas.SimulationResult,
            response_model_exclude_none=True)
def get_simulation(run_id: UUID):
    state = get_state()
    with state.ctx.session_factory() as s:
        runs = SimulationRunRepository(s)
        row = runs.get(run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Unknown simulation run {run_id}")

        result = schemas.SimulationResult(simulation_run_id=row.id, status=row.status)

        change = runs.get_change(run_id)
        if change is not None:
            result.change = schemas.ChangeOut(
                variable_id=change.variable_id, model_route=change.model_route,
                change_type=change.change_type, change_value=str(Decimal(change.change_value)),
            )
        if row.baseline_id is not None:
            bl = BaselineRepository(s).get(row.baseline_id)
            if bl is not None:
                result.baseline = {"id": bl.id, "name": bl.name,
                                   "solve_start": bl.solve_start, "solve_end": bl.solve_end}
        result.model_versions = [
            {"model": v.model_name, "version": v.version_label}
            for v in ModelVersionRepository(s).versions_for_run(run_id)
        ]
        if row.status == "FAILED":
            result.error = {"type": row.error_type or "Unknown",
                            "message": row.error_message or ""}

        tax = TaxResultRepository(s).get_for_run(run_id)
        if tax is not None:
            result.tax_calculator_result = schemas.TaxResultOut(
                tax_year=tax.tax_year, reform=tax.reform,
                base_iitax=str(Decimal(tax.base_iitax)),
                reform_iitax=str(Decimal(tax.reform_iitax)),
                base_payrolltax=str(Decimal(tax.base_payrolltax)),
                reform_payrolltax=str(Decimal(tax.reform_payrolltax)),
                base_combined=str(Decimal(tax.base_combined)),
                reform_combined=str(Decimal(tax.reform_combined)),
                base_agi=str(Decimal(tax.base_agi)),
                taxcalc_version=tax.taxcalc_version,
            )
        adapter = AdapterResultRepository(s).get_for_run(run_id)
        if adapter is not None:
            result.tax_fair_adapter_result = schemas.AdapterResultOut(
                mapping_id=adapter.mapping_id, method=adapter.method,
                source_variable_id=adapter.source_variable_id,
                target_fair_variable=adapter.target_fair_variable,
                fair_change_type=adapter.fair_change_type,
                derived_delta=str(Decimal(adapter.derived_delta)),
                quarterly_allocation_method=adapter.quarterly_allocation_method,
                quarterly_values=list(adapter.quarterly_values),
                conversion_metadata=adapter.conversion_metadata,
            )
        result.metric_deltas = [
            schemas.MetricDeltaOut(
                metric=d.metric, period=d.period,
                baseline=str(d.baseline_value), changed=str(d.changed_value),
                absolute_delta=str(d.absolute_delta),
                percentage_delta=str(d.percentage_delta) if d.percentage_delta is not None else None,
                unit=d.unit,
            )
            for d in MetricRepository(s).get_deltas(run_id)
        ]
        interp = InterpretationRepository(s).get_for_run(run_id)
        if interp is not None:
            result.interpretation = schemas.InterpretationOut(
                model_id=interp.model_id, prompt_version=interp.prompt_version,
                response_text=interp.response_text,
            )
        return result
