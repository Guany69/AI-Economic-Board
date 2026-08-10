"""Test fakes implementing the domain protocols."""

from decimal import Decimal
from typing import Any
from uuid import UUID

from app.config.loader import get_metric_catalog
from app.domain.entities import (
    EconomicChange,
    FairChange,
    LLMInterpretation,
    MetricDelta,
    MetricResult,
    TaxCalculatorResult,
    TaxFairAdapterResult,
)
from app.domain.enums import ChangeType, ModelName
from app.domain.errors import (
    FairExecutionError,
    LLMInterpretationError,
    TaxCalculatorExecutionError,
)
from app.infrastructure.fair.periods import quarter_range


def make_metrics(offset: Decimal = Decimal("0")) -> list[MetricResult]:
    """10 metrics x 14 quarters of synthetic values."""
    catalog = get_metric_catalog()
    periods = quarter_range("2026Q3", "2029Q4")
    out = []
    for i, (name, spec) in enumerate(sorted(catalog.items())):
        for j, period in enumerate(periods):
            out.append(MetricResult(
                model=ModelName.FAIR, metric=name, period=period,
                value=Decimal(100 * (i + 1)) + Decimal(j) + offset,
                unit=spec.unit,
            ))
    return out


class FakeFairRunner:
    def __init__(self, offset: Decimal = Decimal("1.5"), fail: bool = False):
        self.offset = offset
        self.fail = fail
        self.calls: list[FairChange] = []

    def run_scenario(self, run_id: UUID, change: FairChange, baseline: Any) -> list[MetricResult]:
        self.calls.append(change)
        if self.fail:
            raise FairExecutionError("fake Fair failure")
        return make_metrics(self.offset)


class FakeTaxRunner:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls: list[EconomicChange] = []

    def run(self, change: EconomicChange) -> TaxCalculatorResult:
        self.calls.append(change)
        if self.fail:
            raise TaxCalculatorExecutionError("fake Tax-Calculator failure")
        return TaxCalculatorResult(
            tax_year=2026,
            reform={"II_rt1": {2026: 0.08}},
            base_iitax=Decimal("2000000000000"),
            reform_iitax=Decimal("1900000000000"),
            base_payrolltax=Decimal("1500000000000"),
            reform_payrolltax=Decimal("1500000000000"),
            base_combined=Decimal("3500000000000"),
            reform_combined=Decimal("3400000000000"),
            base_agi=Decimal("20000000000000"),
            base_expanded_income=Decimal("25000000000000"),
            total_weight=Decimal("200000000"),
            soi_iitax=False,
            taxcalc_version="6.7.3",
        )


class FakeInterpreter:
    def __init__(self, fail: bool = False, fail_missing_key: bool = False):
        self.fail = fail
        self.fail_missing_key = fail_missing_key
        self.calls: list[list[MetricDelta]] = []

    def interpret(self, change, deltas, tax_result, adapter_result, context):
        self.calls.append(deltas)
        if self.fail_missing_key:
            from app.domain.errors import MissingApiKeyError
            raise MissingApiKeyError()
        if self.fail:
            raise LLMInterpretationError("fake LLM failure")
        return LLMInterpretation(
            model_id="fake-model",
            prompt_version="v1",
            prompt_text="fake prompt",
            response_text="The change raises GDP modestly across the horizon.",
            input_tokens=100, output_tokens=50, stop_reason="end_turn",
        )
