from decimal import Decimal

import pytest

from app.config.loader import (
    load_mapping_table,
    load_metric_catalog,
    load_variable_registry,
)
from app.domain.enums import ChangeType, ModelRoute
from app.domain.errors import ConfigurationError, VariableNotFoundError


@pytest.fixture(scope="module")
def registry():
    return load_variable_registry()


def test_registry_loads_all_expected_variables(registry):
    fair_ids = {v.id for v in registry.all() if v.model_route is ModelRoute.DIRECT_FAIR}
    tax_ids = {v.id for v in registry.all() if v.model_route is ModelRoute.TAX_CALCULATOR}
    assert fair_ids == {
        "COG", "COS", "TRGHQ", "TRSHQ", "TRGSQ", "JG", "JS", "JM",
        "SUBG", "SUBS", "D1G", "D1S", "D2G", "D2S", "D4G", "D5G", "CUST", "RS",
    }
    assert tax_ids == {
        "II_rt1", "II_rt2", "II_rt3", "II_rt4", "II_rt5", "II_rt6", "II_rt7",
        "II_rt_all", "STD", "CTC_c",
        "FICA_ss_trt_employee", "FICA_ss_trt_employer",
        "FICA_mc_trt_employee", "FICA_mc_trt_employer",
    }


def test_rs_requires_exogenous(registry):
    assert registry.get("RS").requires_exogenous is True
    assert registry.get("COG").requires_exogenous is False


def test_composite_variable(registry):
    spec = registry.get("II_rt_all")
    assert spec.param_kind == "composite"
    assert len(spec.composite_of) == 7
    assert ChangeType.SET_VALUE not in spec.allowed_change_types


def test_unknown_variable_raises(registry):
    with pytest.raises(VariableNotFoundError):
        registry.get("NOT_A_VAR")


def test_metric_catalog_has_ten_metrics():
    catalog = load_metric_catalog()
    assert set(catalog) == {"GDP", "GDPR", "UR", "PCGDPD", "YD", "RS", "RB", "RM", "AA", "SGP"}
    assert catalog["GDPR"].unit == "billions of real dollars"


def test_mapping_table():
    table = load_mapping_table()
    m = table.find_for_variable("II_rt_all")
    assert m is not None and m.target_fair_variable == "D1G"
    assert m.method == "EFFECTIVE_RATE_DELTA"
    assert table.find_for_variable("FICA_ss_trt_employee").target_fair_variable == "D4G"
    assert table.find_for_variable("FICA_mc_trt_employer").target_fair_variable == "D5G"
    # CTC_c deliberately has NO mapping (HLD Case F)
    assert table.find_for_variable("CTC_c") is None


def test_loader_fails_fast_on_missing_file(tmp_path):
    with pytest.raises(ConfigurationError):
        load_variable_registry(tmp_path / "missing.yaml")


def test_loader_fails_fast_on_bad_entry(tmp_path):
    bad = tmp_path / "vars.yaml"
    bad.write_text("variables:\n  - id: X\n    label: X\n    model: FAIR\n")
    with pytest.raises(ConfigurationError):
        load_variable_registry(bad)
