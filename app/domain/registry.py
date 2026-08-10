"""Variable registry entities: the typed view of config/economic_variables.yaml.

The registry is the single authority on which economic variables exist, which
model handles them, and which change types/bounds are valid. Nothing here
invents economics — every field is loaded from configuration.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from app.domain.enums import ChangeType, ModelRoute
from app.domain.errors import VariableNotFoundError


@dataclass(frozen=True, slots=True)
class VariableSpec:
    id: str
    label: str
    model_route: ModelRoute
    unit: str
    allowed_change_types: frozenset[ChangeType]
    description: str
    # DIRECT_FAIR variables
    fair_variable: str | None = None
    requires_exogenous: bool = False
    # TAX_CALCULATOR variables
    taxcalc_param: str | None = None
    param_kind: str | None = None          # "scalar" | "mars_vector" | "composite"
    reform_year: int | None = None
    composite_of: tuple[str, ...] = ()
    # optional validation bounds on the *change value*
    min_value: Decimal | None = None
    max_value: Decimal | None = None


@dataclass(frozen=True)
class VariableRegistry:
    variables: dict[str, VariableSpec] = field(default_factory=dict)

    def get(self, variable_id: str) -> VariableSpec:
        try:
            return self.variables[variable_id]
        except KeyError:
            raise VariableNotFoundError(variable_id) from None

    def all(self) -> list[VariableSpec]:
        return sorted(self.variables.values(), key=lambda v: v.id)
