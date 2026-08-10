"""Input validation against the variable registry (HLD Case C: invalid
requests are rejected before any model runs)."""

from decimal import Decimal, InvalidOperation

from app.domain.entities import EconomicChange
from app.domain.enums import ChangeType
from app.domain.errors import ChangeOutOfRangeError, UnsupportedChangeTypeError
from app.domain.registry import VariableRegistry, VariableSpec


class ChangeValidator:
    def __init__(self, registry: VariableRegistry):
        self._registry = registry

    def validate(self, variable_id: str, change_type: str, change_value: object) -> tuple[EconomicChange, VariableSpec]:
        """Validate raw input; returns the typed change and its spec.

        Raises VariableNotFoundError / UnsupportedChangeTypeError /
        ChangeOutOfRangeError — all ValidationError subclasses.
        """
        spec = self._registry.get(variable_id)  # VariableNotFoundError

        try:
            ct = ChangeType(change_type)
        except ValueError:
            raise UnsupportedChangeTypeError(
                variable_id, str(change_type), sorted(t.value for t in spec.allowed_change_types)
            ) from None
        if ct not in spec.allowed_change_types:
            raise UnsupportedChangeTypeError(
                variable_id, ct.value, sorted(t.value for t in spec.allowed_change_types)
            )

        try:
            value = Decimal(str(change_value))
        except (InvalidOperation, ValueError, TypeError):
            raise ChangeOutOfRangeError(variable_id, f"not a number: {change_value!r}") from None
        if not value.is_finite():
            raise ChangeOutOfRangeError(variable_id, f"not finite: {change_value!r}")
        if ct in (ChangeType.ABSOLUTE, ChangeType.PERCENT) and value == 0:
            raise ChangeOutOfRangeError(variable_id, "a zero delta is not a change")

        # Bounds apply to the delta itself for ABSOLUTE, and to the target
        # value for SET_VALUE. PERCENT deltas are sanity-capped at +/-100%.
        if ct is ChangeType.PERCENT and abs(value) > 100:
            raise ChangeOutOfRangeError(variable_id, f"PERCENT change {value} outside [-100, 100]")
        if ct in (ChangeType.ABSOLUTE, ChangeType.SET_VALUE):
            if spec.min_value is not None and value < spec.min_value:
                raise ChangeOutOfRangeError(variable_id, f"{value} < min {spec.min_value}")
            if spec.max_value is not None and value > spec.max_value:
                raise ChangeOutOfRangeError(variable_id, f"{value} > max {spec.max_value}")

        return EconomicChange(variable_id=variable_id, change_type=ct, change_value=value), spec
