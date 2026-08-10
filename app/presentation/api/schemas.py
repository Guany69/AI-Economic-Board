"""API request/response schemas (presentation shapes only)."""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChangeIn(BaseModel):
    type: Literal["ABSOLUTE", "PERCENT", "SET_VALUE"]
    value: float | str


class SimulationRequest(BaseModel):
    variable_id: str = Field(min_length=1, max_length=64)
    change: ChangeIn
    horizon_quarters: int | None = None


class SubmissionResponse(BaseModel):
    simulation_run_id: UUID
    status: str


class VariableOut(BaseModel):
    id: str
    label: str
    model: str
    unit: str
    allowed_change_types: list[str]
    description: str


class MetricDeltaOut(BaseModel):
    metric: str
    period: str
    baseline: str
    changed: str
    absolute_delta: str
    percentage_delta: str | None
    unit: str


class TaxResultOut(BaseModel):
    tax_year: int
    reform: dict[str, Any]
    base_iitax: str
    reform_iitax: str
    base_payrolltax: str
    reform_payrolltax: str
    base_combined: str
    reform_combined: str
    base_agi: str
    taxcalc_version: str


class AdapterResultOut(BaseModel):
    mapping_id: str
    method: str
    source_variable_id: str
    target_fair_variable: str
    fair_change_type: str
    derived_delta: str
    quarterly_allocation_method: str
    quarterly_values: list[str]
    conversion_metadata: dict[str, Any]


class InterpretationOut(BaseModel):
    model_id: str
    prompt_version: str
    response_text: str


class ChangeOut(BaseModel):
    variable_id: str
    model_route: str
    change_type: str
    change_value: str


class SimulationResult(BaseModel):
    simulation_run_id: UUID
    status: str
    change: ChangeOut | None = None
    baseline: dict[str, Any] | None = None
    model_versions: list[dict[str, Any]] = []
    error: dict[str, str] | None = None
    tax_calculator_result: TaxResultOut | None = None
    tax_fair_adapter_result: AdapterResultOut | None = None
    metric_deltas: list[MetricDeltaOut] = []
    interpretation: InterpretationOut | None = None
