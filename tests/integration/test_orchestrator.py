"""Orchestrator integration tests against real PostgreSQL with fake models.

Covers HLD acceptance cases at the orchestration level:
  A: direct Fair change end-to-end (Tax-Calculator does NOT run)
  D: missing baseline -> safe failure, no model runs
  E: Tax-Calculator failure -> FAILED, no fabricated adapter data
  F: undefined Tax-to-Fair mapping -> FAILED before taxcalc/Fair run
  G: Fair failure -> FAILED, LLM never invoked
  H: LLM failure -> FAILED, deterministic results retained
"""

from decimal import Decimal

import pytest

from app.application.context import AppContext
from app.application.orchestrator import SimulationOrchestrator
from app.business.comparison import MetricComparisonService
from app.business.routing import ChangeRouter
from app.business.validation import ChangeValidator
from app.config.loader import get_variable_registry
from app.config.settings import get_settings
from app.domain.enums import ModelName, RunStatus
from app.domain.errors import BaselineNotFoundError, VariableNotFoundError
from app.infrastructure.adapters.tax_to_fair import ConfiguredTaxToFairAdapter
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
from tests.fakes import FakeFairRunner, FakeInterpreter, FakeTaxRunner, make_metrics


@pytest.fixture()
def ctx(session_factory):
    registry = get_variable_registry()
    return AppContext(
        settings=get_settings(),
        registry=registry,
        validator=ChangeValidator(registry),
        router=ChangeRouter(registry),
        comparison=MetricComparisonService(),
        fair_runner=FakeFairRunner(),
        tax_runner=FakeTaxRunner(),
        tax_adapter=ConfiguredTaxToFairAdapter(),
        interpreter=FakeInterpreter(),
        session_factory=session_factory,
    )


@pytest.fixture()
def seeded_baseline(session_factory, tmp_path):
    snap = tmp_path / "BASE.BIN"
    snap.write_bytes(b"fake snapshot")
    with session_factory() as s:
        mv = ModelVersionRepository(s)
        fair_id = mv.get_or_create(ModelName.FAIR, "fake-fair", {})
        art_id = ArtifactRepository(s).register(fair_id, "BASE.BIN", str(snap), "0" * 64, 13)
        bl = BaselineRepository(s)
        bid = bl.create("fake-baseline", fair_id, "2026Q3", "2029Q4", art_id)
        bl.add_metrics(bid, make_metrics())
        s.commit()
    return bid


def _run_to_completion(ctx, variable_id, change_type, value):
    orch = SimulationOrchestrator(ctx)
    sub = orch.submit(variable_id, change_type, value)
    orch.execute(sub.run_id)
    return sub.run_id


# ---------------------------------------------------------------- Case A
def test_case_a_direct_fair_end_to_end(ctx, seeded_baseline):
    run_id = _run_to_completion(ctx, "COG", "ABSOLUTE", 25)
    with ctx.session_factory() as s:
        row = SimulationRunRepository(s).get(run_id)
        assert row.status == "COMPLETED"
        assert ctx.tax_runner.calls == []                       # taxcalc did NOT run
        assert len(ctx.fair_runner.calls) == 1
        assert ctx.fair_runner.calls[0].fair_variable == "COG"
        metrics = MetricRepository(s).get_simulation_metrics(run_id)
        assert len(metrics) == 140
        deltas = MetricRepository(s).get_deltas(run_id)
        assert len(deltas) == 140
        assert all(d.absolute_delta == Decimal("1.5") for d in deltas)
        interp = InterpretationRepository(s).get_for_run(run_id)
        assert interp is not None and "GDP" in interp.response_text
        # LLM ran only after deltas existed
        assert ctx.interpreter.calls and len(ctx.interpreter.calls[0]) == 140


# ---------------------------------------------------------------- Case B (fake-level)
def test_case_b_tax_path_end_to_end(ctx, seeded_baseline):
    run_id = _run_to_completion(ctx, "II_rt_all", "ABSOLUTE", "-0.02")
    with ctx.session_factory() as s:
        assert SimulationRunRepository(s).get(run_id).status == "COMPLETED"
        tax_row = TaxResultRepository(s).get_for_run(run_id)
        assert tax_row is not None
        adapter_row = AdapterResultRepository(s).get_for_run(run_id)
        assert adapter_row is not None
        assert adapter_row.target_fair_variable == "D1G"
        assert adapter_row.method == "EFFECTIVE_RATE_DELTA"
        # derived delta = (1.9e12 - 2.0e12) / 2.0e13 = -0.005
        assert Decimal(adapter_row.derived_delta) == Decimal("-0.005")
        assert len(adapter_row.quarterly_values) == 14
        # the Fair run used the adapted change, not the raw tax input
        assert ctx.fair_runner.calls[0].fair_variable == "D1G"
        assert ctx.fair_runner.calls[0].value == Decimal("-0.005")


# ---------------------------------------------------------------- Case C
def test_case_c_invalid_variable_rejected_before_any_model(ctx, seeded_baseline):
    orch = SimulationOrchestrator(ctx)
    with pytest.raises(VariableNotFoundError):
        orch.submit("BOGUS", "ABSOLUTE", 1)
    assert ctx.fair_runner.calls == []
    assert ctx.tax_runner.calls == []
    with ctx.session_factory() as s:
        assert SimulationRunRepository(s).find_by_status(RunStatus.PENDING) == []


# ---------------------------------------------------------------- Case D
def test_case_d_missing_baseline_no_model_runs(ctx):
    orch = SimulationOrchestrator(ctx)
    with pytest.raises(BaselineNotFoundError):
        orch.submit("COG", "ABSOLUTE", 25)
    assert ctx.fair_runner.calls == []
    assert ctx.tax_runner.calls == []
    with ctx.session_factory() as s:
        assert SimulationRunRepository(s).find_by_status(RunStatus.PENDING) == []


# ---------------------------------------------------------------- Case E
def test_case_e_taxcalc_failure(ctx, seeded_baseline):
    ctx.tax_runner = FakeTaxRunner(fail=True)
    run_id = _run_to_completion(ctx, "II_rt_all", "ABSOLUTE", "-0.02")
    with ctx.session_factory() as s:
        row = SimulationRunRepository(s).get(run_id)
        assert row.status == "FAILED"
        assert row.error_type == "TaxCalculatorExecutionError"
        # no fabricated downstream data
        assert TaxResultRepository(s).get_for_run(run_id) is None
        assert AdapterResultRepository(s).get_for_run(run_id) is None
        assert MetricRepository(s).get_simulation_metrics(run_id) == []
    assert ctx.fair_runner.calls == []


# ---------------------------------------------------------------- Case F
def test_case_f_unmapped_tax_variable_fails_before_taxcalc(ctx, seeded_baseline):
    run_id = _run_to_completion(ctx, "CTC_c", "ABSOLUTE", 500)
    with ctx.session_factory() as s:
        row = SimulationRunRepository(s).get(run_id)
        assert row.status == "FAILED"
        assert row.error_type == "TaxToFairMappingError"
        assert "never" in row.error_message.lower() or "refusing" in row.error_message.lower()
        assert TaxResultRepository(s).get_for_run(run_id) is None
    assert ctx.tax_runner.calls == []      # fail-fast: taxcalc never ran
    assert ctx.fair_runner.calls == []


# ---------------------------------------------------------------- Case G
def test_case_g_fair_failure_llm_never_invoked(ctx, seeded_baseline):
    ctx.fair_runner = FakeFairRunner(fail=True)
    run_id = _run_to_completion(ctx, "COG", "ABSOLUTE", 25)
    with ctx.session_factory() as s:
        row = SimulationRunRepository(s).get(run_id)
        assert row.status == "FAILED"
        assert row.error_type == "FairExecutionError"
        assert MetricRepository(s).get_simulation_metrics(run_id) == []
        assert MetricRepository(s).get_deltas(run_id) == []
    assert ctx.interpreter.calls == []


# ---------------------------------------------------------------- Case H
def test_case_h_llm_failure_retains_deterministic_results(ctx, seeded_baseline):
    ctx.interpreter = FakeInterpreter(fail_missing_key=True)
    run_id = _run_to_completion(ctx, "COG", "ABSOLUTE", 25)
    with ctx.session_factory() as s:
        row = SimulationRunRepository(s).get(run_id)
        assert row.status == "FAILED"
        assert row.error_type == "MissingApiKeyError"
        # deterministic results retained
        assert len(MetricRepository(s).get_simulation_metrics(run_id)) == 140
        assert len(MetricRepository(s).get_deltas(run_id)) == 140
        assert InterpretationRepository(s).get_for_run(run_id) is None


# ---------------------------------------------------------------- versions
def test_model_versions_linked(ctx, seeded_baseline):
    run_id = _run_to_completion(ctx, "II_rt_all", "ABSOLUTE", "-0.02")
    with ctx.session_factory() as s:
        versions = ModelVersionRepository(s).versions_for_run(run_id)
        names = {v.model_name for v in versions}
        assert names == {"FAIR", "TAX_CALCULATOR"}
