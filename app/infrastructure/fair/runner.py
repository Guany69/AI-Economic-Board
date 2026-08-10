"""Executes the compiled Fair fp binary and enforces its success contract."""

import re
import subprocess
from pathlib import Path

from app.config.settings import Settings, get_settings
from app.domain.errors import FairExecutionError

# Fatal patterns. NOTE: the benign data-load message is 'Name X not found.'
# (with 'Name added to list'); fatal variants are distinct.
FATAL_PATTERNS = (
    "Solution error",
    "ERROR IN RD",
    "COMMAND PARAMETER NOT RECOGNIZED",
    "Variable name not found",
)
_CMD_NOT_FOUND = re.compile(r"Command name .* not found", re.IGNORECASE)
_ITERS = re.compile(r"^ ITERS=", re.MULTILINE)


def run_fp(stage: Path, stdin_text: str, log_name: str,
           expected_iters: int | None, settings: Settings | None = None) -> Path:
    """Run fp in `stage` feeding `stdin_text`; write the log; enforce checks.

    Returns the log path. Raises FairExecutionError on any contract breach.
    """
    settings = settings or get_settings()
    fp = settings.fp_binary
    if not fp.is_file():
        raise FairExecutionError(
            f"Fair fp binary not found at {fp}. Run scripts/build_fair.sh "
            "(or set ECON_FP_BINARY)."
        )
    log_path = stage / log_name
    try:
        proc = subprocess.run(
            [str(fp)],
            input=stdin_text.encode(),
            cwd=stage,
            capture_output=True,
            timeout=settings.fair_timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or b"").decode(errors="replace")
        log_path.write_text(partial)
        raise FairExecutionError(
            f"Fair fp timed out after {settings.fair_timeout_seconds}s "
            f"(scratch dir retained: {stage})"
        ) from None

    log = proc.stdout.decode(errors="replace") + proc.stderr.decode(errors="replace")
    log_path.write_text(log)

    def _excerpt(pattern: str) -> str:
        lines = [ln for ln in log.splitlines() if pattern.lower() in ln.lower()]
        return "; ".join(lines[:3])

    if proc.returncode != 0:
        raise FairExecutionError(
            f"Fair fp exited with code {proc.returncode}; log tail: "
            f"{log[-500:]} (scratch dir retained: {stage})"
        )
    for pattern in FATAL_PATTERNS:
        if pattern.lower() in log.lower():
            raise FairExecutionError(
                f"Fair fp reported {pattern!r}: {_excerpt(pattern)} "
                f"(full log: {log_path})"
            )
    if _CMD_NOT_FOUND.search(log):
        raise FairExecutionError(
            f"Fair fp did not recognize a command (full log: {log_path})"
        )
    if expected_iters is not None:
        n = len(_ITERS.findall(log))
        if n != expected_iters:
            raise FairExecutionError(
                f"Fair fp solve produced {n} ITERS lines, expected "
                f"{expected_iters} (full log: {log_path})"
            )
    return log_path
