"""Domain error hierarchy.

Every failure mode the HLD requires to be explicit has a dedicated type.
The orchestrator persists ``type(exc).__name__`` as ``error_type`` on the
simulation run, so these names are part of the external contract.
"""


class DomainError(Exception):
    """Base class for all domain-level failures."""


# --- validation (HLD Case C) -------------------------------------------------

class ValidationError(DomainError):
    """Base for input-validation failures; no model may run after these."""


class VariableNotFoundError(ValidationError):
    def __init__(self, variable_id: str):
        self.variable_id = variable_id
        super().__init__(f"Unknown economic variable: {variable_id!r}")


class UnsupportedChangeTypeError(ValidationError):
    def __init__(self, variable_id: str, change_type: str, allowed: list[str]):
        self.variable_id = variable_id
        self.change_type = change_type
        super().__init__(
            f"Change type {change_type!r} is not allowed for variable "
            f"{variable_id!r}; allowed: {allowed}"
        )


class ChangeOutOfRangeError(ValidationError):
    def __init__(self, variable_id: str, message: str):
        self.variable_id = variable_id
        super().__init__(f"Change for {variable_id!r} out of range: {message}")


# --- baseline (HLD Case D) ---------------------------------------------------

class BaselineNotFoundError(DomainError):
    def __init__(self, message: str = "No ACTIVE baseline exists; create one with 'econ baseline-create'"):
        super().__init__(message)


# --- model execution (HLD Cases E/G) ------------------------------------------

class TaxCalculatorExecutionError(DomainError):
    """Tax-Calculator run failed; no adapter data may be fabricated."""


class FairExecutionError(DomainError):
    """Fair fp run failed (non-zero exit, error strings, missing output)."""


class FairOutputParseError(DomainError):
    """Fair FILEWRITE output did not match the expected format."""


# --- adapter (HLD Case F) ------------------------------------------------------

class TaxToFairMappingError(DomainError):
    """No defined Tax-to-Fair mapping exists for the requested change.

    Raised BEFORE Tax-Calculator runs (fail-fast) and re-checked at derive
    time. Mappings are never guessed or invented.
    """

    def __init__(self, variable_id: str, reason: str):
        self.variable_id = variable_id
        super().__init__(
            f"No Tax-to-Fair mapping defined for {variable_id!r}: {reason}. "
            "Refusing to guess an economic conversion."
        )


# --- LLM (HLD Case H) ----------------------------------------------------------

class LLMInterpretationError(DomainError):
    """LLM interpretation failed; deterministic results are retained."""


class MissingApiKeyError(LLMInterpretationError):
    def __init__(self):
        super().__init__(
            "ANTHROPIC_API_KEY is not set; cannot run LLM interpretation. "
            "Deterministic model results and metric deltas are retained."
        )


# --- state machine --------------------------------------------------------------

class InvalidStateTransitionError(DomainError):
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"Invalid simulation state transition: {from_status} -> {to_status}")


# --- configuration ----------------------------------------------------------------

class ConfigurationError(DomainError):
    """Invalid or missing configuration/registry/mapping files."""
