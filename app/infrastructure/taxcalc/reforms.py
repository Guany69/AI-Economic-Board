"""Builds Tax-Calculator reform dictionaries from validated economic changes.

Targets are computed against 2026 current-law values read from the vendored
Policy object — never hard-coded.
"""

from decimal import Decimal

import numpy as np

from app.domain.entities import EconomicChange
from app.domain.enums import ChangeType
from app.domain.errors import ChangeOutOfRangeError, TaxCalculatorExecutionError
from app.domain.registry import VariableSpec


def _target_scalar(current: float, change: EconomicChange) -> float:
    v = float(change.change_value)
    if change.change_type is ChangeType.ABSOLUTE:
        return current + v
    if change.change_type is ChangeType.PERCENT:
        return current * (1 + v / 100)
    return v  # SET_VALUE


def build_reform(change: EconomicChange, spec: VariableSpec, policy) -> dict:
    """Return a taxcalc reform dict {param: {year: value}}.

    `policy` is a taxcalc.Policy positioned at the reform year.
    """
    year = spec.reform_year
    assert year is not None

    if spec.param_kind == "composite":
        reform: dict = {}
        for sub in spec.composite_of:
            current = float(np.asarray(getattr(policy, sub)).ravel()[0])
            target = _target_scalar(current, change)
            _check_rate_bounds(sub, target)
            reform[sub] = {year: target}
        return reform

    if spec.param_kind == "mars_vector":
        current = np.asarray(getattr(policy, spec.taxcalc_param)).ravel()
        if change.change_type is ChangeType.ABSOLUTE:
            target = [float(c) + float(change.change_value) for c in current]
        elif change.change_type is ChangeType.PERCENT:
            target = [float(c) * (1 + float(change.change_value) / 100) for c in current]
        else:
            raise ChangeOutOfRangeError(spec.id, "SET_VALUE not supported for MARS vectors")
        if any(t < 0 for t in target):
            raise ChangeOutOfRangeError(spec.id, f"reform would make {spec.taxcalc_param} negative")
        return {spec.taxcalc_param: {year: target}}

    # scalar
    current = float(np.asarray(getattr(policy, spec.taxcalc_param)).ravel()[0])
    target = _target_scalar(current, change)
    if spec.taxcalc_param.startswith(("II_rt", "FICA_")):
        _check_rate_bounds(spec.taxcalc_param, target)
    elif target < 0:
        raise ChangeOutOfRangeError(spec.id, f"reform would make {spec.taxcalc_param} negative")
    return {spec.taxcalc_param: {year: target}}


def _check_rate_bounds(param: str, target: float) -> None:
    if not (0.0 <= target <= 1.0):
        raise ChangeOutOfRangeError(
            param, f"reform would set {param} to {target}, outside [0, 1]"
        )
