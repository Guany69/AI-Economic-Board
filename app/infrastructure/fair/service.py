"""FairModelRunner: the MacroModelRunner implementation.

Scenario flow (fast path, verified): stage dir with model files + BASE.BIN
from the active baseline -> fp reads 'READJOB FILE=BASE.BIN' from stdin,
restoring the solved base state without re-estimation -> INPUT of the
generated scenario body (SMPL / EXOGENOUS / CHANGEVAR / SOLVE FILEWRITE)
-> parse SCENOUT.TXT into MetricResults.
"""

import logging
from pathlib import Path
from uuid import UUID

from app.config.loader import get_metric_catalog
from app.config.settings import Settings, get_settings
from app.domain.entities import FairChange, MetricResult
from app.infrastructure.fair import scripts
from app.infrastructure.fair.parser import parse_filewrite
from app.infrastructure.fair.runner import run_fp
from app.infrastructure.fair.staging import cleanup_run_dir, stage_run_dir

logger = logging.getLogger(__name__)


class FairModelRunner:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.metrics = list(get_metric_catalog())

    def run_scenario(self, run_id: UUID, change: FairChange, baseline) -> list[MetricResult]:
        """`baseline` must expose `.snapshot_path` (Path to BASE.BIN)."""
        s = self.settings
        stage = stage_run_dir(f"run-{run_id}", s, snapshot=Path(baseline.snapshot_path))
        body = scripts.build_scenario_body(change, self.metrics, s.solve_start, s.solve_end)
        (stage / scripts.SCENARIO_BODY_FILE).write_text(body)
        logger.info("Fair scenario for run %s: %s %s %s", run_id,
                    change.fair_variable, change.change_type.value, change.value)
        run_fp(stage, scripts.scenario_stdin(), "SCEN.LOG",
               expected_iters=s.horizon_quarters, settings=s)
        results = parse_filewrite(
            stage / scripts.SCENARIO_OUTPUT_FILE, self.metrics, get_metric_catalog(),
            s.solve_start, s.solve_end, s.horizon_quarters,
        )
        cleanup_run_dir(stage)  # success only; failures keep the dir for diagnosis
        return results
