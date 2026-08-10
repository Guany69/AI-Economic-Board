"""Baseline builder: run the full Fair base job (load + estimate + solve),
snapshot the state, and persist the baseline + metrics + provenance.

This is the slow, full-estimation path, run locally via
`econ baseline-create`, never during a simulation request.
"""

import logging
from datetime import datetime, timezone

from app.config.loader import get_metric_catalog
from app.config.settings import Settings, get_settings
from app.domain.enums import ModelName
from app.infrastructure.artifacts import store
from app.infrastructure.fair import scripts
from app.infrastructure.fair.parser import parse_filewrite
from app.infrastructure.fair.runner import run_fp
from app.infrastructure.fair.staging import MODEL_FILES, stage_run_dir
from app.infrastructure.persistence.db import open_session
from app.infrastructure.persistence.repositories import (
    ArtifactRepository,
    BaselineRepository,
    ModelVersionRepository,
)

logger = logging.getLogger(__name__)


def create_baseline(name: str | None = None, settings: Settings | None = None) -> int:
    settings = settings or get_settings()
    name = name or f"baseline-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"
    catalog = get_metric_catalog()
    metrics = list(catalog)

    # 1. stage + generate the base job
    stage = stage_run_dir(f"baseline-{name}", settings)
    fminput_text = (stage / "FMINPUT.TXT").read_text()
    job = scripts.build_base_job(fminput_text, metrics,
                                 settings.solve_start, settings.solve_end)
    (stage / scripts.BASE_JOB_FILE).write_text(job)

    # 2. run fp (full estimation + solve; two solves -> 2x horizon ITERS lines)
    logger.info("Running Fair base job in %s", stage)
    run_fp(stage, scripts.base_stdin(), "BASE.LOG",
           expected_iters=2 * settings.horizon_quarters, settings=settings)

    # 3. parse baseline metrics
    results = parse_filewrite(stage / scripts.BASE_OUTPUT_FILE, metrics, catalog,
                              settings.solve_start, settings.solve_end,
                              settings.horizon_quarters)

    # 4. archive the snapshot and register provenance
    archive_dir = settings.fair_artifacts_dir / name
    snapshot_info = store.archive(stage / scripts.BASE_SNAPSHOT_FILE, archive_dir)
    input_infos = [
        store.describe(settings.fair_model_dir / rel, staged)
        for rel, staged in MODEL_FILES.items()
    ]
    fp_info = store.describe(settings.fp_binary, "fp")

    import taxcalc  # vendored; version recorded for provenance

    with open_session() as session:
        mv = ModelVersionRepository(session)
        fair_version_id = mv.get_or_create(
            ModelName.FAIR,
            "fair-fp-2013-11-11/us-model-2026-07-31",
            {
                "program": "Fair-Parke Program November 11, 2013",
                "model": "US MODEL JULY 31, 2026",
                "solve_window": [settings.solve_start, settings.solve_end],
                "fp_sha256": fp_info.sha256,
            },
        )
        mv.get_or_create(ModelName.TAX_CALCULATOR, f"taxcalc-{taxcalc.__version__}",
                         {"vendored": True})
        art = ArtifactRepository(session)
        snapshot_artifact_id = art.register(
            fair_version_id, "BASE.BIN", str(snapshot_info.path),
            snapshot_info.sha256, snapshot_info.size_bytes,
        )
        for info in input_infos:
            art.register(fair_version_id, info.name, str(info.path),
                         info.sha256, info.size_bytes)
        art.register(fair_version_id, "fp", str(fp_info.path),
                     fp_info.sha256, fp_info.size_bytes)

        bl = BaselineRepository(session)
        bl.retire_all_active()
        baseline_id = bl.create(name, fair_version_id, settings.solve_start,
                                settings.solve_end, snapshot_artifact_id)
        bl.add_metrics(baseline_id, results)
        session.commit()

    logger.info("Baseline %s (id=%s) created: %d metric rows",
                name, baseline_id, len(results))
    return baseline_id
