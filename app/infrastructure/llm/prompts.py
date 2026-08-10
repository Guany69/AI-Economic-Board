"""Versioned prompt construction for LLM interpretation.

The prompt renders the completed deterministic results. The system prompt
forbids the model from inventing or recomputing numbers (HLD invariant 8).
Rendering is deterministic: same inputs -> same prompt text.
"""

from typing import Any

from app.domain.entities import (
    EconomicChange,
    MetricDelta,
    TaxCalculatorResult,
    TaxFairAdapterResult,
)

PROMPT_VERSION = "v1"

SYSTEM_V1 = (
    "You are the economic interpretation service of a deterministic "
    "simulation system built on the Ray Fair macroeconometric model (with "
    "Tax-Calculator microsimulation for tax-policy inputs). You receive "
    "metric results and deltas that were already computed by the models. "
    "These numbers are final: never recompute, adjust, extrapolate, or "
    "invent numerical results. Your job is interpretation only — explain "
    "direction, relative magnitude, the economic channels likely at work, "
    "notable dynamics across the horizon, and important caveats. Cite "
    "numbers exactly as given. If something cannot be explained from the "
    "provided data, say so explicitly rather than guessing."
)


def render_user_prompt(
    change: EconomicChange,
    deltas: list[MetricDelta],
    tax_result: TaxCalculatorResult | None,
    adapter_result: TaxFairAdapterResult | None,
    context: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("## Simulation request")
    lines.append(
        f"Variable: {change.variable_id}; change type: {change.change_type.value}; "
        f"change value: {change.change_value}"
    )
    lines.append(
        f"Baseline: {context.get('baseline_name', 'unknown')}; solve window: "
        f"{context.get('solve_start')}..{context.get('solve_end')}; "
        f"Fair variable shocked: {context.get('fair_variable')}"
    )

    if tax_result is not None:
        lines.append("")
        lines.append("## Tax-Calculator results (aggregate, weighted)")
        lines.append(f"Tax year: {tax_result.tax_year}; reform: {tax_result.reform}")
        lines.append(
            f"iitax: base {tax_result.base_iitax} -> reform {tax_result.reform_iitax}; "
            f"payrolltax: base {tax_result.base_payrolltax} -> reform "
            f"{tax_result.reform_payrolltax}; combined: base {tax_result.base_combined} "
            f"-> reform {tax_result.reform_combined}"
        )
    if adapter_result is not None:
        lines.append("")
        lines.append("## Tax-to-Fair adapter")
        lines.append(
            f"Mapping {adapter_result.mapping_id} ({adapter_result.method}): "
            f"{adapter_result.source_variable_id} -> "
            f"{adapter_result.target_fair_variable} "
            f"{adapter_result.fair_change_type.value} {adapter_result.derived_delta} "
            f"(allocation: {adapter_result.quarterly_allocation_method})"
        )

    lines.append("")
    lines.append("## Metric deltas (baseline vs changed, per quarter)")
    lines.append("metric | period | baseline | changed | absolute_delta | percentage_delta | unit")
    for d in deltas:
        pct = f"{d.percentage_delta}%" if d.percentage_delta is not None else "n/a"
        lines.append(
            f"{d.metric} | {d.period} | {d.baseline_value} | {d.changed_value} | "
            f"{d.absolute_delta} | {pct} | {d.unit}"
        )

    lines.append("")
    lines.append(
        "Interpret these results in economic terms: direction and magnitude of "
        "effects, likely transmission channels, dynamics over the horizon, and "
        "caveats. Do not restate the whole table; do not invent numbers."
    )
    return "\n".join(lines)
