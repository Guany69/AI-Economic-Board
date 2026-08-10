"""SimulationOrchestrator: coordinates the HLD workflow with bounded
transactions — no model executes inside an open DB transaction.

Flow per run:
  TX1  submit: insert PENDING run + economic change
  TX2  PENDING->RUNNING + model-version links
  (free) route; tax route: ensure_mapping (fail-fast) -> Tax-Calculator
  TX3a   persist tax results
  (free) derive Fair change via the explicit adapter
  TX3b   persist adapter result
  (free) Fair scenario run (ALWAYS — every scenario goes through Ray Fair)
  TX4    persist changed simulation metrics
  (free) deterministic comparison vs stored baseline metrics
  TX5    persist metric deltas
  (free) LLM interpretation (only after deterministic deltas exist)
  TX6    persist interpretation + RUNNING->COMPLETED
  On any exception: mark FAILED with error type/message; all committed
  work is retained.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from app.application.context import AppContext
from app.domain.entities import EconomicChange, SimulationSubmission
from app.domain.enums import ChangeType, ModelName, ModelRoute, RunStatus
from app.domain.errors import BaselineNotFoundError, DomainError
from app.infrastructure.persistence.repositories import (
    AdapterResultRepository,
    ArtifactRepository,
    BaselineRepository,
    InterpretationRepository,
    MetricRepository,
    ModelVersionRepository,
    SimulationRunRepository,
    TaxResultRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BaselineHandle:
    id: int
    name: str
    snapshot_path: Path


class SimulationOrchestrator:
    def __init__(self, ctx: AppContext):
        self.ctx = ctx

    # ------------------------------------------------------------- submit
    def submit(self, variable_id: str, change_type: str, change_value: object,
               horizon_quarters: int | None = None) -> SimulationSubmission:
        """Validate and persist a new PENDING run. Raises ValidationError
        (Case C) or BaselineNotFoundError (Case D) BEFORE anything runs."""
        change, spec = self.ctx.validator.validate(variable_id, change_type, change_value)
        route = self.ctx.router.route(change)
        horizon = horizon_quarters or self.ctx.settings.horizon_quarters
        if horizon != self.ctx.settings.horizon_quarters:
            raise DomainError(
                f"Only the fixed {self.ctx.settings.horizon_quarters}-quarter "
                "solve window is supported in the MVP"
            )
        with self.ctx.session_factory() as session:
            baseline = BaselineRepository(session).get_active()  # Case D
            run_id = SimulationRunRepository(session).create(
                baseline.id, change, route, horizon
            )
            session.commit()
        logger.info("Run %s submitted: %s %s %s (route %s)", run_id,
                    variable_id, change_type, change_value, route.value)
        return SimulationSubmission(run_id=run_id, status=RunStatus.PENDING.value)

    # ------------------------------------------------------------- execute
    def execute(self, run_id: UUID) -> None:
        """Execute one PENDING run to COMPLETED or FAILED. Never raises."""
        try:
            self._execute_inner(run_id)
        except Exception as exc:  # noqa: BLE001 — every failure must land in the DB
            logger.exception("Run %s failed: %s", run_id, exc)
            with self.ctx.session_factory() as session:
                SimulationRunRepository(session).fail_from_any_active(
                    run_id, type(exc).__name__, str(exc)
                )
                session.commit()

    def _execute_inner(self, run_id: UUID) -> None:
        ctx = self.ctx

        # TX2: claim the run
        with ctx.session_factory() as session:
            runs = SimulationRunRepository(session)
            runs.transition(run_id, RunStatus.PENDING, RunStatus.RUNNING)
            change_row = runs.get_change(run_id)
            run_row = runs.get(run_id)
            baseline_row = BaselineRepository(session).get(run_row.baseline_id)
            if baseline_row is None:
                raise BaselineNotFoundError(f"Baseline {run_row.baseline_id} vanished")
            snapshot = ArtifactRepository(session).get(baseline_row.snapshot_artifact_id)
            mv = ModelVersionRepository(session)
            fair_v = mv.get_or_create(ModelName.FAIR, "fair-fp-2013-11-11/us-model-2026-07-31", {})
            mv.link_to_run(run_id, fair_v)
            route = ModelRoute(change_row.model_route)
            if route is ModelRoute.TAX_CALCULATOR:
                import taxcalc
                tax_v = mv.get_or_create(ModelName.TAX_CALCULATOR,
                                         f"taxcalc-{taxcalc.__version__}", {"vendored": True})
                mv.link_to_run(run_id, tax_v)
            session.commit()

        change = EconomicChange(
            variable_id=change_row.variable_id,
            change_type=ChangeType(change_row.change_type),
            change_value=Decimal(change_row.change_value),
        )
        baseline = BaselineHandle(
            id=baseline_row.id, name=baseline_row.name,
            snapshot_path=Path(snapshot.path) if snapshot else None,
        )

        tax_result = None
        adapter_result = None
        if route is ModelRoute.TAX_CALCULATOR:
            # fail-fast BEFORE the expensive model run (Case F)
            ctx.tax_adapter.ensure_mapping(change)
            tax_result = ctx.tax_runner.run(change)          # Case E on failure
            with ctx.session_factory() as session:            # TX3a
                tax_row_id = TaxResultRepository(session).add(run_id, tax_result)
                session.commit()
            adapter_result = ctx.tax_adapter.derive(change, tax_result)
            with ctx.session_factory() as session:            # TX3b
                AdapterResultRepository(session).add(run_id, tax_row_id, adapter_result)
                session.commit()
            spec = ctx.registry.get(adapter_result.target_fair_variable) \
                if adapter_result.target_fair_variable in ctx.registry.variables else None
            fair_change = adapter_result.to_fair_change(
                requires_exogenous=bool(spec and spec.requires_exogenous)
            )
        else:
            fair_change = ctx.router.to_fair_change(change)

        # Fair ALWAYS runs the changed scenario (Case G on failure)
        changed_metrics = ctx.fair_runner.run_scenario(run_id, fair_change, baseline)
        with ctx.session_factory() as session:                # TX4
            MetricRepository(session).add_simulation_metrics(run_id, changed_metrics)
            session.commit()

        # deterministic comparison against STORED baseline metrics
        with ctx.session_factory() as session:
            baseline_metrics = BaselineRepository(session).get_metrics(baseline.id)
        deltas = ctx.comparison.compare(baseline_metrics, changed_metrics)
        with ctx.session_factory() as session:                # TX5
            MetricRepository(session).add_deltas(run_id, deltas)
            session.commit()

        # LLM interpretation — strictly after deterministic results (Case H)
        interpretation = ctx.interpreter.interpret(
            change, deltas, tax_result, adapter_result,
            context={
                "baseline_name": baseline.name,
                "solve_start": ctx.settings.solve_start,
                "solve_end": ctx.settings.solve_end,
                "fair_variable": fair_change.fair_variable,
            },
        )
        with ctx.session_factory() as session:                # TX6
            InterpretationRepository(session).add(run_id, interpretation)
            SimulationRunRepository(session).transition(
                run_id, RunStatus.RUNNING, RunStatus.COMPLETED
            )
            session.commit()
        logger.info("Run %s COMPLETED", run_id)
