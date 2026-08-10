from decimal import Decimal

import pytest

from app.business.comparison import MetricComparisonService
from app.domain.entities import MetricResult
from app.domain.enums import ModelName


def _mr(metric, period, value, unit="u"):
    return MetricResult(model=ModelName.FAIR, metric=metric, period=period,
                        value=Decimal(value), unit=unit)


def test_deltas_are_exact_decimals():
    svc = MetricComparisonService()
    deltas = svc.compare(
        [_mr("GDP", "2026Q3", "6584.05")],
        [_mr("GDP", "2026Q3", "6614.572")],
    )
    d = deltas[0]
    assert d.absolute_delta == Decimal("30.522")
    assert d.percentage_delta == Decimal("0.4635748513")
    assert d.baseline_value == Decimal("6584.05")


def test_zero_baseline_yields_null_percentage():
    svc = MetricComparisonService()
    d = svc.compare([_mr("SGP", "2026Q3", "0")], [_mr("SGP", "2026Q3", "-5.5")])[0]
    assert d.absolute_delta == Decimal("-5.5")
    assert d.percentage_delta is None


def test_negative_baseline_percentage_signed_correctly():
    svc = MetricComparisonService()
    d = svc.compare([_mr("SGP", "2026Q3", "-100")], [_mr("SGP", "2026Q3", "-110")])[0]
    assert d.absolute_delta == Decimal("-10")
    assert d.percentage_delta == Decimal("10")  # -10 / -100 * 100


def test_missing_baseline_pair_raises():
    svc = MetricComparisonService()
    with pytest.raises(ValueError):
        svc.compare([_mr("GDP", "2026Q3", "1")], [_mr("GDP", "2026Q4", "2")])
