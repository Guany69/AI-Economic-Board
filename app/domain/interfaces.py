"""Protocols implemented by the infrastructure layer.

The application/business layers depend only on these, never on concrete
model runners, so model-specific code stays behind explicit adapters.
"""

from typing import Any, Protocol
from uuid import UUID

from app.domain.entities import (
    EconomicChange,
    FairChange,
    LLMInterpretation,
    MetricDelta,
    MetricResult,
    TaxCalculatorResult,
    TaxFairAdapterResult,
)


class MacroModelRunner(Protocol):
    """Runs the Ray Fair model for a changed scenario."""

    def run_scenario(self, run_id: UUID, change: FairChange, baseline: Any) -> list[MetricResult]:
        """Solve the changed scenario against the given baseline snapshot.

        Returns changed metric results for the full solve window.
        Raises FairExecutionError / FairOutputParseError on failure.
        """
        ...


class TaxModelRunner(Protocol):
    """Runs Tax-Calculator for an applicable tax-policy change."""

    def run(self, change: EconomicChange) -> TaxCalculatorResult:
        """Raises TaxCalculatorExecutionError on failure."""
        ...


class TaxToFairAdapter(Protocol):
    """Explicit conversion of Tax-Calculator output to a Fair variable change."""

    def ensure_mapping(self, change: EconomicChange) -> None:
        """Raise TaxToFairMappingError if no mapping is defined (fail-fast,
        called BEFORE the expensive Tax-Calculator run)."""
        ...

    def derive(self, change: EconomicChange, tax_result: TaxCalculatorResult) -> TaxFairAdapterResult:
        """Raises TaxToFairMappingError if the mapping is undefined."""
        ...


class LLMInterpreter(Protocol):
    """Interprets completed deterministic results. Never computes numbers."""

    def interpret(
        self,
        change: EconomicChange,
        deltas: list[MetricDelta],
        tax_result: TaxCalculatorResult | None,
        adapter_result: TaxFairAdapterResult | None,
        context: dict[str, Any],
    ) -> LLMInterpretation:
        """Raises LLMInterpretationError (incl. MissingApiKeyError) on failure."""
        ...
