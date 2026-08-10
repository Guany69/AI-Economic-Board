"""Parses Fair FILEWRITE output.

Format (verified against the compiled binary): repeating groups of one
variable-name line (A8) followed by the values, four per line (F19.10).
The value series covers fp's internal output window and ENDS at the solve
window's last quarter; the solve-window values are the trailing slice.
"""

from decimal import Decimal
from pathlib import Path

from app.config.loader import MetricSpec
from app.domain.entities import MetricResult
from app.domain.enums import ModelName
from app.domain.errors import FairOutputParseError
from app.infrastructure.fair.periods import quarter_seq_ending


def parse_filewrite(path: Path, expected_metrics: list[str],
                    catalog: dict[str, MetricSpec],
                    solve_start: str, solve_end: str,
                    horizon: int) -> list[MetricResult]:
    path = Path(path)
    if not path.is_file():
        raise FairOutputParseError(f"Fair output file missing: {path}")
    text = path.read_text()
    if not text.strip():
        raise FairOutputParseError(f"Fair output file is empty: {path}")

    series: dict[str, list[Decimal]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        # a name line starts at column 1 with a non-numeric token
        first = line.split()[0]
        is_name = line[0] not in " \t" and not _is_number(first)
        if is_name:
            current = first
            if current in series:
                raise FairOutputParseError(f"Duplicate variable {current!r} in {path}")
            series[current] = []
        else:
            if current is None:
                raise FairOutputParseError(f"Values before any variable name in {path}")
            for token in line.split():
                try:
                    series[current].append(Decimal(token))
                except ArithmeticError:
                    raise FairOutputParseError(
                        f"Bad numeric token {token!r} for {current!r} in {path}"
                    ) from None

    missing = [m for m in expected_metrics if m not in series]
    if missing:
        raise FairOutputParseError(f"Metrics missing from Fair output {path}: {missing}")

    results: list[MetricResult] = []
    for metric in expected_metrics:
        values = series[metric]
        if len(values) < horizon:
            raise FairOutputParseError(
                f"Metric {metric!r} has {len(values)} values, need >= {horizon}"
            )
        window = values[-horizon:]
        periods = quarter_seq_ending(solve_end, horizon)
        if periods[0] != solve_start:
            raise FairOutputParseError(
                f"Solve window mismatch: derived start {periods[0]}, expected {solve_start}"
            )
        unit = catalog[metric].unit if metric in catalog else ""
        for period, value in zip(periods, window):
            results.append(MetricResult(model=ModelName.FAIR, metric=metric,
                                        period=period, value=value, unit=unit))
    return results


def _is_number(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False
