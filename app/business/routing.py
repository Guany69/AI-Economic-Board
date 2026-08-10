"""Routing rules: which workflow a change follows and how change types map
to Fair CHANGEVAR operations."""

from app.domain.entities import EconomicChange, FairChange
from app.domain.enums import ChangeType, ModelRoute
from app.domain.registry import VariableRegistry

# HLD-fixed mapping of change types onto Fair's CHANGEVAR operations.
CHANGEVAR_OPS: dict[ChangeType, str] = {
    ChangeType.ABSOLUTE: "ADDSAMEABS",
    ChangeType.PERCENT: "ADDSAMEPCT",
    ChangeType.SET_VALUE: "SAMEVALUE",
}


class ChangeRouter:
    def __init__(self, registry: VariableRegistry):
        self._registry = registry

    def route(self, change: EconomicChange) -> ModelRoute:
        return self._registry.get(change.variable_id).model_route

    def to_fair_change(self, change: EconomicChange) -> FairChange:
        """Build the FairChange for a DIRECT_FAIR variable."""
        spec = self._registry.get(change.variable_id)
        assert spec.model_route is ModelRoute.DIRECT_FAIR, (
            f"{change.variable_id} is not a direct Fair variable"
        )
        assert spec.fair_variable is not None
        return FairChange(
            fair_variable=spec.fair_variable,
            change_type=change.change_type,
            value=change.change_value,
            requires_exogenous=spec.requires_exogenous,
        )
