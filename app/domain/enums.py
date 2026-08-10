"""Core enumerations shared across all layers."""

from enum import StrEnum


class RunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ChangeType(StrEnum):
    ABSOLUTE = "ABSOLUTE"
    PERCENT = "PERCENT"
    SET_VALUE = "SET_VALUE"


class ModelRoute(StrEnum):
    """Which workflow a validated economic change follows.

    DIRECT_FAIR: the variable is a Fair model exogenous variable; the change
    is applied directly in the Fair scenario script.
    TAX_CALCULATOR: the variable is a Tax-Calculator policy parameter; the
    change runs through Tax-Calculator and must be explicitly adapted to a
    Fair variable before the Fair scenario runs.
    """

    DIRECT_FAIR = "DIRECT_FAIR"
    TAX_CALCULATOR = "TAX_CALCULATOR"


class ModelName(StrEnum):
    FAIR = "FAIR"
    TAX_CALCULATOR = "TAX_CALCULATOR"
    LLM = "LLM"


class BaselineStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
