"""TaxCalculatorRunner: runs the vendored Tax-Calculator (library API) for an
applicable tax-policy change and returns aggregate results.

Pattern (verified against vendored taxcalc 6.7.3):
  Policy() -> Records.cps_constructor(gfactors=GrowFactors()) ->
  Calculator -> advance_to_year(2026) -> calc_all() -> weighted_total(...)

Notes:
- GrowFactors() is passed explicitly (mutable-default singleton gotcha).
- Baseline and reform run strictly sequentially (~1.5 GB peak).
- The vendored 6.7.3 has no `soi_iitax` switch; self-employment (SECA)
  taxes bucket into payrolltax — recorded as soi_iitax=False.
"""

import logging
import warnings
from decimal import Decimal

from app.config.settings import Settings, get_settings
from app.config.loader import get_variable_registry
from app.domain.entities import EconomicChange, TaxCalculatorResult
from app.domain.errors import TaxCalculatorExecutionError
from app.infrastructure.taxcalc.reforms import build_reform

logger = logging.getLogger(__name__)


def _dec(x) -> Decimal:
    return Decimal(repr(float(x)))


class TaxCalculatorRunner:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def run(self, change: EconomicChange) -> TaxCalculatorResult:
        spec = get_variable_registry().get(change.variable_id)
        year = spec.reform_year or self.settings.taxcalc_year
        try:
            import taxcalc as tc

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                base_policy = tc.Policy()
                base_policy.set_year(year)
                reform = build_reform(change, spec, base_policy)

                logger.info("Tax-Calculator reform for %s: %s", change.variable_id, reform)
                records = tc.Records.cps_constructor(gfactors=tc.GrowFactors())

                base_calc = tc.Calculator(policy=base_policy, records=records)
                base_calc.advance_to_year(year)
                base_calc.calc_all()
                base = {
                    "iitax": base_calc.weighted_total("iitax"),
                    "payrolltax": base_calc.weighted_total("payrolltax"),
                    "combined": base_calc.weighted_total("combined"),
                    "agi": base_calc.weighted_total("c00100"),
                    "expanded_income": base_calc.weighted_total("expanded_income"),
                    "weight": base_calc.total_weight(),
                }
                del base_calc  # release before the reform pass (memory)

                reform_policy = tc.Policy()
                reform_policy.implement_reform(reform)
                reform_calc = tc.Calculator(policy=reform_policy, records=records)
                reform_calc.advance_to_year(year)
                reform_calc.calc_all()
                ref = {
                    "iitax": reform_calc.weighted_total("iitax"),
                    "payrolltax": reform_calc.weighted_total("payrolltax"),
                    "combined": reform_calc.weighted_total("combined"),
                }
                del reform_calc

            return TaxCalculatorResult(
                tax_year=year,
                reform=reform,
                base_iitax=_dec(base["iitax"]),
                reform_iitax=_dec(ref["iitax"]),
                base_payrolltax=_dec(base["payrolltax"]),
                reform_payrolltax=_dec(ref["payrolltax"]),
                base_combined=_dec(base["combined"]),
                reform_combined=_dec(ref["combined"]),
                base_agi=_dec(base["agi"]),
                base_expanded_income=_dec(base["expanded_income"]),
                total_weight=_dec(base["weight"]),
                soi_iitax=False,
                taxcalc_version=tc.__version__,
            )
        except TaxCalculatorExecutionError:
            raise
        except Exception as exc:
            # ChangeOutOfRangeError etc. propagate as-is; anything from the
            # model itself becomes an explicit execution failure (Case E).
            from app.domain.errors import ValidationError
            if isinstance(exc, ValidationError):
                raise
            raise TaxCalculatorExecutionError(
                f"Tax-Calculator run failed for {change.variable_id}: {exc}"
            ) from exc
