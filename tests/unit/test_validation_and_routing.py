from decimal import Decimal

import pytest

from app.business.routing import CHANGEVAR_OPS, ChangeRouter
from app.business.validation import ChangeValidator
from app.config.loader import load_variable_registry
from app.domain.enums import ChangeType, ModelRoute
from app.domain.errors import (
    ChangeOutOfRangeError,
    UnsupportedChangeTypeError,
    VariableNotFoundError,
)


@pytest.fixture(scope="module")
def registry():
    return load_variable_registry()


@pytest.fixture(scope="module")
def validator(registry):
    return ChangeValidator(registry)


@pytest.fixture(scope="module")
def router(registry):
    return ChangeRouter(registry)


def test_valid_direct_fair_change(validator, router):
    change, spec = validator.validate("COG", "ABSOLUTE", 25)
    assert change.change_value == Decimal("25")
    assert router.route(change) is ModelRoute.DIRECT_FAIR
    fc = router.to_fair_change(change)
    assert fc.fair_variable == "COG"
    assert fc.requires_exogenous is False


def test_valid_tax_change_routes_to_taxcalc(validator, router):
    change, _ = validator.validate("II_rt_all", "ABSOLUTE", "-0.02")
    assert router.route(change) is ModelRoute.TAX_CALCULATOR


def test_rs_fair_change_is_exogenous(validator, router):
    change, _ = validator.validate("RS", "ABSOLUTE", "0.5")
    assert router.to_fair_change(change).requires_exogenous is True


def test_unknown_variable(validator):
    with pytest.raises(VariableNotFoundError):
        validator.validate("BOGUS", "ABSOLUTE", 1)


def test_unsupported_change_type(validator):
    with pytest.raises(UnsupportedChangeTypeError):
        validator.validate("II_rt_all", "SET_VALUE", 0.2)


def test_garbage_change_type(validator):
    with pytest.raises(UnsupportedChangeTypeError):
        validator.validate("COG", "TRIPLE", 1)


def test_non_numeric_value(validator):
    with pytest.raises(ChangeOutOfRangeError):
        validator.validate("COG", "ABSOLUTE", "abc")


def test_zero_delta_rejected(validator):
    with pytest.raises(ChangeOutOfRangeError):
        validator.validate("COG", "ABSOLUTE", 0)


def test_bounds_enforced(validator):
    with pytest.raises(ChangeOutOfRangeError):
        validator.validate("D1G", "ABSOLUTE", "0.9")   # max 0.5


def test_percent_capped(validator):
    with pytest.raises(ChangeOutOfRangeError):
        validator.validate("COG", "PERCENT", 150)


def test_changevar_ops_complete():
    assert CHANGEVAR_OPS == {
        ChangeType.ABSOLUTE: "ADDSAMEABS",
        ChangeType.PERCENT: "ADDSAMEPCT",
        ChangeType.SET_VALUE: "SAMEVALUE",
    }
