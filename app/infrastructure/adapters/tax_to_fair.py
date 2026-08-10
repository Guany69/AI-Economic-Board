"""ConfiguredTaxToFairAdapter: the explicit, persisted conversion of
Tax-Calculator output into a Fair model variable change.

Only mappings defined in config/tax_to_fair_mapping.yaml exist. Anything
else raises TaxToFairMappingError — conversions are never guessed
(HLD invariant 11 / Case F). ensure_mapping() runs BEFORE Tax-Calculator so
unmapped requests fail fast without an expensive model run.
"""

from decimal import Decimal

import numpy as np

from app.config.loader import MappingSpec, get_mapping_table, get_variable_registry
from app.config.settings import get_settings
from app.domain.entities import EconomicChange, TaxCalculatorResult, TaxFairAdapterResult
from app.domain.enums import ChangeType
from app.domain.errors import TaxToFairMappingError

QUANT = Decimal("0.0000000001")


class ConfiguredTaxToFairAdapter:
    def __init__(self, mapping_table=None):
        self._table = mapping_table or get_mapping_table()

    def _find(self, change: EconomicChange) -> MappingSpec:
        mapping = self._table.find_for_variable(change.variable_id)
        if mapping is None:
            raise TaxToFairMappingError(
                change.variable_id,
                "variable is not listed in config/tax_to_fair_mapping.yaml",
            )
        return mapping

    def ensure_mapping(self, change: EconomicChange) -> None:
        self._find(change)

    def derive(self, change: EconomicChange,
               tax_result: TaxCalculatorResult) -> TaxFairAdapterResult:
        mapping = self._find(change)
        if mapping.method == "EFFECTIVE_RATE_DELTA":
            delta, metadata = self._effective_rate_delta(tax_result)
        elif mapping.method == "STATUTORY_RATE_PASSTHROUGH":
            delta, metadata = self._statutory_passthrough(change, tax_result)
        else:  # pragma: no cover — loader validates methods
            raise TaxToFairMappingError(change.variable_id,
                                        f"unknown method {mapping.method!r}")

        horizon = get_settings().horizon_quarters
        return TaxFairAdapterResult(
            mapping_id=mapping.id,
            method=mapping.method,
            source_variable_id=change.variable_id,
            target_fair_variable=mapping.target_fair_variable,
            fair_change_type=mapping.fair_change_type,
            derived_delta=delta,
            quarterly_allocation_method=mapping.allocation,
            quarterly_values=tuple([delta] * horizon),
            conversion_metadata=metadata,
        )

    # ------------------------------------------------------------- methods
    def _effective_rate_delta(self, tax: TaxCalculatorResult) -> tuple[Decimal, dict]:
        if tax.base_agi == 0:
            raise TaxToFairMappingError(
                "EFFECTIVE_RATE_DELTA", "baseline AGI is zero; cannot derive a rate"
            )
        delta = ((tax.reform_iitax - tax.base_iitax) / tax.base_agi).quantize(QUANT)
        metadata = {
            "formula": "(reform_iitax - base_iitax) / base_agi(c00100)",
            "base_iitax": str(tax.base_iitax),
            "reform_iitax": str(tax.reform_iitax),
            "base_agi": str(tax.base_agi),
            "tax_year": tax.tax_year,
            "taxcalc_version": tax.taxcalc_version,
            "notes": (
                "MVP calibration: iitax/AGI is level-commensurate with Fair's "
                "D1G average effective federal personal income tax rate."
            ),
        }
        return delta, metadata

    def _statutory_passthrough(self, change: EconomicChange,
                               tax: TaxCalculatorResult) -> tuple[Decimal, dict]:
        # The reform dict holds the absolute target rate; the implied
        # absolute statutory delta is target - current-law.
        param = get_variable_registry().get(change.variable_id).taxcalc_param
        if param not in tax.reform:
            raise TaxToFairMappingError(
                change.variable_id, f"reform dict lacks parameter {param!r}"
            )
        (year_map,) = [tax.reform[param]]
        target = Decimal(repr(float(np.asarray(list(year_map.values())[0]).ravel()[0])))
        current = self._current_law_rate(param, tax.tax_year)
        delta = (target - current).quantize(QUANT)
        metadata = {
            "formula": "target_statutory_rate - current_law_rate",
            "taxcalc_param": param,
            "current_law_rate": str(current),
            "target_rate": str(target),
            "tax_year": tax.tax_year,
            "taxcalc_version": tax.taxcalc_version,
            "caveats": (
                "Fair's D4G/D5G apply to total wages without the OASDI taxable "
                "maximum; SECA self-employment taxes bucket into payrolltax in "
                "the vendored Tax-Calculator (no soi_iitax switch)."
            ),
        }
        return delta, metadata

    @staticmethod
    def _current_law_rate(param: str, year: int) -> Decimal:
        import warnings

        import taxcalc as tc

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pol = tc.Policy()
            pol.set_year(year)
            return Decimal(repr(float(np.asarray(getattr(pol, param)).ravel()[0])))
