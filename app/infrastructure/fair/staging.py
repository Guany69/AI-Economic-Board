"""Fair run staging: every fp invocation gets its own scratch directory with
UPPERCASE copies of the model files; all fp side effects stay inside it.
Scratch dirs are retained on failure for diagnosis."""

import shutil
from pathlib import Path

from app.config.settings import Settings, get_settings

# vendored source name -> staged UPPERCASE name (fp requires <=15 chars, uppercase)
MODEL_FILES = {
    "Definition/fminput.txt": "FMINPUT.TXT",
    "Data/fmdata.txt": "FMDATA.TXT",
    "Data/fmexog.txt": "FMEXOG.TXT",
    "Data/fmage.txt": "FMAGE.TXT",
}


def stage_run_dir(name: str, settings: Settings | None = None,
                  snapshot: Path | None = None) -> Path:
    """Create data/runtime/fair/<name>/ with the staged model inputs.

    `snapshot` (BASE.BIN from the active baseline) is copied in for
    scenario runs.
    """
    settings = settings or get_settings()
    stage = settings.fair_runtime_dir / name
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for rel, staged_name in MODEL_FILES.items():
        src = settings.fair_model_dir / rel
        if not src.is_file():
            raise FileNotFoundError(f"Vendored Fair model file missing: {src}")
        shutil.copy2(src, stage / staged_name)
    if snapshot is not None:
        if not Path(snapshot).is_file():
            raise FileNotFoundError(f"Baseline snapshot missing: {snapshot}")
        shutil.copy2(snapshot, stage / "BASE.BIN")
    return stage


def cleanup_run_dir(stage: Path) -> None:
    shutil.rmtree(stage, ignore_errors=True)
