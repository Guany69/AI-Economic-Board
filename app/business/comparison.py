"""MetricComparisonService: deterministic baseline-vs-changed comparison.

Pure Decimal arithmetic — no floats, no LLM (HLD invariant 7). The
percentage delta is None when the baseline value is zero.
"""

from decimal import Decimal

from app.domain.entities import MetricDelta, MetricResult

PCT_QUANT = Decimal("0.0000000001")  # 10 dp, matches NUMERIC(24,10)


class MetricComparisonService:
    def compare(self, baseline: list[MetricResult],
                changed: list[MetricResult]) -> list[MetricDelta]:
        base_map = {(m.metric, m.period): m for m in baseline}
        deltas: list[MetricDelta] = []
        for ch in changed:
            key = (ch.metric, ch.period)
            if key not in base_map:
                raise ValueError(
                    f"Baseline is missing metric/period {key}; cannot compare"
                )
            base = base_map[key]
            absolute = ch.value - base.value
            if base.value == 0:
                pct = None
            else:
                pct = (absolute / base.value * 100).quantize(PCT_QUANT)
            deltas.append(MetricDelta(
                metric=ch.metric, period=ch.period,
                baseline_value=base.value, changed_value=ch.value,
                absolute_delta=absolute, percentage_delta=pct,
                unit=ch.unit or base.unit,
            ))
        return deltas
