from decimal import Decimal
from pathlib import Path

import pytest

from app.config.loader import load_metric_catalog
from app.domain.entities import FairChange
from app.domain.enums import ChangeType
from app.domain.errors import FairOutputParseError
from app.infrastructure.fair import scripts
from app.infrastructure.fair.parser import parse_filewrite
from app.infrastructure.fair.periods import quarter_range, quarter_seq_ending, to_fair_period

METRICS = ["GDP", "UR"]


def test_quarter_helpers():
    assert quarter_seq_ending("2029Q4", 14)[0] == "2026Q3"
    assert quarter_range("2026Q3", "2027Q2") == ["2026Q3", "2026Q4", "2027Q1", "2027Q2"]
    assert to_fair_period("2026Q3") == "2026.3"


def test_base_job_golden():
    fminput = "LOADDATA FILE=FMDATA.TXT;\nEST 1;\nSETYYTOY;\nPRINTMODEL;\nQUIT;\n"
    job = scripts.build_base_job(fminput, METRICS, "2026Q3", "2029Q4")
    assert job.startswith("LOADDATA FILE=FMDATA.TXT;\nEST 1;\nSETYYTOY;")
    # everything after SETYYTOY is replaced
    assert "PRINTMODEL" not in job
    assert "WRITEJOB FILE=BASE.BIN;" in job
    assert "SMPL 2026.3 2029.4;" in job
    assert "SOLVE DYNAMIC OUTSIDE NORESET FILEWRITE=BASEOUT.TXT FILEVAR=KEYBOARD;" in job
    assert "GDP\nUR\n;" in job
    assert job.rstrip().endswith("QUIT;")


def test_base_job_requires_setyytoy():
    with pytest.raises(ValueError):
        scripts.build_base_job("EST 1;\nQUIT;\n", METRICS, "2026Q3", "2029Q4")


def test_scenario_body_absolute_golden():
    change = FairChange("COG", ChangeType.ABSOLUTE, Decimal("25.0"))
    body = scripts.build_scenario_body(change, METRICS, "2026Q3", "2029Q4")
    assert body == (
        "SMPL 2026.3 2029.4;\n"
        "CHANGEVAR;\n"
        "COG ADDSAMEABS\n"
        "25.0\n"
        ";\n"
        "SOLVE DYNAMIC OUTSIDE NORESET FILEWRITE=SCENOUT.TXT FILEVAR=KEYBOARD;\n"
        "GDP\nUR\n;\nQUIT;\n"
    )


def test_scenario_body_percent_converts_to_fraction():
    change = FairChange("COG", ChangeType.PERCENT, Decimal("10"))
    body = scripts.build_scenario_body(change, METRICS, "2026Q3", "2029Q4")
    assert "COG ADDSAMEPCT\n0.1\n" in body


def test_scenario_body_set_value():
    change = FairChange("D1G", ChangeType.SET_VALUE, Decimal("0.13"))
    body = scripts.build_scenario_body(change, METRICS, "2026Q3", "2029Q4")
    assert "D1G SAMEVALUE\n0.13\n" in body


def test_scenario_body_exogenous():
    change = FairChange("RS", ChangeType.ABSOLUTE, Decimal("0.5"), requires_exogenous=True)
    body = scripts.build_scenario_body(change, METRICS, "2026Q3", "2029Q4")
    assert "EXOGENOUS VARIABLE=RS;" in body
    assert body.index("EXOGENOUS") < body.index("CHANGEVAR")


def test_stdin_forms():
    assert scripts.base_stdin() == "INPUT FILE=BASEJOB.TXT ;\n"
    assert scripts.scenario_stdin() == "READJOB FILE=BASE.BIN ;\nINPUT FILE=SCENBODY.TXT ;\n"


def _write_filewrite(path: Path, n_quarters: int = 30):
    # 30 values, 4 per line, F19.10-ish
    lines = ["GDP     "]
    vals = [1000 + i for i in range(n_quarters)]
    for i in range(0, n_quarters, 4):
        lines.append("".join(f"{v:19.10f}" for v in vals[i:i + 4]))
    lines.append("UR      ")
    urs = [0.04 + 0.001 * i for i in range(n_quarters)]
    for i in range(0, n_quarters, 4):
        lines.append("".join(f"{v:19.10f}" for v in urs[i:i + 4]))
    path.write_text("\n".join(lines) + "\n")


def test_parser_slices_solve_window(tmp_path):
    out = tmp_path / "OUT.TXT"
    _write_filewrite(out)
    catalog = load_metric_catalog()
    results = parse_filewrite(out, METRICS, catalog, "2026Q3", "2029Q4", 14)
    assert len(results) == 28
    gdp = [r for r in results if r.metric == "GDP"]
    assert gdp[0].period == "2026Q3"
    assert gdp[-1].period == "2029Q4"
    assert gdp[0].value == Decimal("1016.0000000000")  # index 16 of 30
    assert gdp[0].unit == "billions of dollars"


def test_parser_missing_metric(tmp_path):
    out = tmp_path / "OUT.TXT"
    _write_filewrite(out)
    with pytest.raises(FairOutputParseError):
        parse_filewrite(out, ["GDP", "UR", "AA"], load_metric_catalog(),
                        "2026Q3", "2029Q4", 14)


def test_parser_empty_file(tmp_path):
    out = tmp_path / "OUT.TXT"
    out.write_text("")
    with pytest.raises(FairOutputParseError):
        parse_filewrite(out, METRICS, load_metric_catalog(), "2026Q3", "2029Q4", 14)


def test_parser_short_series(tmp_path):
    out = tmp_path / "OUT.TXT"
    _write_filewrite(out, n_quarters=8)
    with pytest.raises(FairOutputParseError):
        parse_filewrite(out, METRICS, load_metric_catalog(), "2026Q3", "2029Q4", 14)
