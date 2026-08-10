"""Domain entities passed between layers.

These are plain frozen dataclasses — no ORM, no pydantic — so business logic
stays framework-free. Numeric metric values are Decimal end to end: metric
deltas are deterministic calculations and must not pick up float noise.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.domain.enums import ChangeType, ModelName, ModelRoute


@dataclass(frozen=True, slots=True)
class EconomicChange:
    """The user's request: one economic variable plus a proposed delta."""

    variable_id: str
    change_type: ChangeType
    change_value: Decimal


@dataclass(frozen=True, slots=True)
class FairChange:
    """A concrete change applied in a Fair scenario script."""

    fair_variable: str          # UPPERCASE Fair variable name, e.g. "COG"
    change_type: ChangeType     # mapped to ADDSAMEABS / ADDSAMEPCT / SAMEVALUE
    value: Decimal
    requires_exogenous: bool = False


@dataclass(frozen=True, slots=True)
class MetricResult:
    """One metric value for one period from one model run."""

    model: ModelName
    metric: str                 # canonical metric name, e.g. "GDPR"
    period: str                 # canonical period, e.g. "2026Q3"
    value: Decimal
    unit: str


@dataclass(frozen=True, slots=True)
class MetricDelta:
    """Deterministic comparison of one metric/period: baseline vs changed."""

    metric: str
    period: str
    baseline_value: Decimal
    changed_value: Decimal
    absolute_delta: Decimal
    percentage_delta: Decimal | None    # None when baseline_value == 0
    unit: str


@dataclass(frozen=True, slots=True)
class TaxCalculatorResult:
    """Aggregates from a Tax-Calculator baseline-vs-reform run."""

    tax_year: int
    reform: dict[str, Any]              # the taxcalc reform dict actually applied
    base_iitax: Decimal
    reform_iitax: Decimal
    base_payrolltax: Decimal
    reform_payrolltax: Decimal
    base_combined: Decimal
    reform_combined: Decimal
    base_agi: Decimal                   # weighted total of c00100 under baseline
    base_expanded_income: Decimal
    total_weight: Decimal
    soi_iitax: bool
    taxcalc_version: str


@dataclass(frozen=True, slots=True)
class TaxFairAdapterResult:
    """Explicit, persisted conversion of Tax-Calculator output to a FairChange."""

    mapping_id: str
    method: str                         # e.g. "EFFECTIVE_RATE_DELTA"
    source_variable_id: str
    target_fair_variable: str
    fair_change_type: ChangeType
    derived_delta: Decimal
    quarterly_allocation_method: str    # e.g. "CONSTANT"
    quarterly_values: tuple[Decimal, ...]
    conversion_metadata: dict[str, Any] = field(default_factory=dict)

    def to_fair_change(self, requires_exogenous: bool = False) -> FairChange:
        return FairChange(
            fair_variable=self.target_fair_variable,
            change_type=self.fair_change_type,
            value=self.derived_delta,
            requires_exogenous=requires_exogenous,
        )


@dataclass(frozen=True, slots=True)
class LLMInterpretation:
    model_id: str
    prompt_version: str
    prompt_text: str
    response_text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    stop_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SimulationSubmission:
    """Returned by the orchestrator when a run is accepted."""

    run_id: UUID
    status: str
