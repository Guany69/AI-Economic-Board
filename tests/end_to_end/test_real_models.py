"""Real-model tests (slow): executes the compiled Fair fp binary and the
vendored Tax-Calculator. Auto-skipped when the fp binary is missing.

Run with: pytest -m real_models
"""

import shutil
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.config.loader import get_metric_catalog
from app.config.settings import get_settings
from app.domain.entities import EconomicChange, FairChange
from app.domain.enums import ChangeType
from app.infrastructure.fair import scripts
from app.infrastructure.fair.parser import parse_filewrite
from app.infrastructure.fair.runner import run_fp
from app.infrastructure.fair.service import FairModelRunner
from app.infrastructure.fair.staging import cleanup_run_dir, stage_run_dir

pytestmark = pytest.mark.real_models

settings = get_settings()

needs_fp = pytest.mark.skipif(
    not settings.fp_binary.is_file(),
    reason="fp binary not built (run scripts/build_fair.sh)",
)


@pytest.fixture(scope="module")
def base_snapshot(tmp_path_factory):
    """Run the full base job once; yields (BASE.BIN path, base metrics)."""
    stage = stage_run_dir("test-base", settings)
    fminput = (stage / "FMINPUT.TXT").read_text()
    metrics = list(get_metric_catalog())
    job = scripts.build_base_job(fminput, metrics, settings.solve_start, settings.solve_end)
    (stage / scripts.BASE_JOB_FILE).write_text(job)
    run_fp(stage, scripts.base_stdin(), "BASE.LOG",
           expected_iters=2 * settings.horizon_quarters, settings=settings)
    results = parse_filewrite(stage / scripts.BASE_OUTPUT_FILE, metrics,
                              get_metric_catalog(), settings.solve_start,
                              settings.solve_end, settings.horizon_quarters)
    keep = tmp_path_factory.mktemp("snapshot")
    shutil.copy2(stage / scripts.BASE_SNAPSHOT_FILE, keep / "BASE.BIN")
    cleanup_run_dir(stage)
    yield keep / "BASE.BIN", results


class _Handle:
    def __init__(self, path):
        self.id = 0
        self.name = "test"
        self.snapshot_path = path


@needs_fp
def test_readjob_determinism_gate(base_snapshot):
    """READJOB + zero-change solve must reproduce base metrics exactly."""
    snapshot, base_metrics = base_snapshot
    stage = stage_run_dir("test-determinism", settings, snapshot=snapshot)
    metrics = list(get_metric_catalog())
    body = (
        f"SMPL 2026.3 2029.4;\n"
        f"SOLVE DYNAMIC OUTSIDE NORESET FILEWRITE={scripts.SCENARIO_OUTPUT_FILE} "
        f"FILEVAR=KEYBOARD;\n" + "\n".join(metrics) + "\n;\nQUIT;\n"
    )
    (stage / scripts.SCENARIO_BODY_FILE).write_text(body)
    run_fp(stage, scripts.scenario_stdin(), "DET.LOG",
           expected_iters=settings.horizon_quarters, settings=settings)
    results = parse_filewrite(stage / scripts.SCENARIO_OUTPUT_FILE, metrics,
                              get_metric_catalog(), settings.solve_start,
                              settings.solve_end, settings.horizon_quarters)
    assert {(m.metric, m.period): m.value for m in results} == \
           {(m.metric, m.period): m.value for m in base_metrics}
    cleanup_run_dir(stage)


@needs_fp
def test_real_direct_fair_scenario(base_snapshot):
    """COG +25 through the real FairModelRunner: sensible fiscal multiplier."""
    snapshot, base_metrics = base_snapshot
    runner = FairModelRunner(settings)
    change = FairChange("COG", ChangeType.ABSOLUTE, Decimal("25"))
    results = runner.run_scenario(uuid.uuid4(), change, _Handle(snapshot))
    assert len(results) == 140
    base = {(m.metric, m.period): m.value for m in base_metrics}
    gdp_deltas = [m.value - base[("GDP", m.period)] for m in results if m.metric == "GDP"]
    assert all(d > 0 for d in gdp_deltas)          # spending raises nominal GDP
    assert Decimal("10") < gdp_deltas[0] < Decimal("100")
    ur_deltas = [m.value - base[("UR", m.period)] for m in results if m.metric == "UR"]
    assert ur_deltas[2] < 0                        # unemployment falls


@needs_fp
def test_real_rs_exogenous_scenario(base_snapshot):
    snapshot, base_metrics = base_snapshot
    runner = FairModelRunner(settings)
    change = FairChange("RS", ChangeType.ABSOLUTE, Decimal("0.5"), requires_exogenous=True)
    results = runner.run_scenario(uuid.uuid4(), change, _Handle(snapshot))
    base = {(m.metric, m.period): m.value for m in base_metrics}
    rs_deltas = [m.value - base[("RS", m.period)] for m in results if m.metric == "RS"]
    assert all(abs(d - Decimal("0.5")) < Decimal("0.0001") for d in rs_deltas)


def test_real_taxcalc_effective_rate_plausibility():
    """II_rt_all -0.02 through the real Tax-Calculator + adapter: the derived
    D1G delta must be negative and within a plausible band."""
    from app.infrastructure.adapters.tax_to_fair import ConfiguredTaxToFairAdapter
    from app.infrastructure.taxcalc.runner import TaxCalculatorRunner

    change = EconomicChange("II_rt_all", ChangeType.ABSOLUTE, Decimal("-0.02"))
    result = TaxCalculatorRunner(settings).run(change)
    assert result.reform_iitax < result.base_iitax
    adapter = ConfiguredTaxToFairAdapter()
    derived = adapter.derive(change, result)
    assert derived.target_fair_variable == "D1G"
    # a 2pp cut in every bracket should move the average effective rate by
    # roughly -0.5pp..-3pp, never more than the statutory cut itself
    assert Decimal("-0.03") < derived.derived_delta < Decimal("-0.005")
    assert len(derived.quarterly_values) == 14
