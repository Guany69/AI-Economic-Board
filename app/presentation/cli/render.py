"""Plain-text rendering for the econ CLI."""

import textwrap


def render_variables(variables: list[dict]) -> str:
    lines = [f"{'ID':22s} {'MODEL':15s} {'TYPES':28s} {'UNIT':26s} LABEL"]
    for v in variables:
        types = ",".join(v["allowed_change_types"])
        lines.append(f"{v['id']:22s} {v['model']:15s} {types:28s} {v['unit']:26s} {v['label']}")
    return "\n".join(lines)


def _fmt(value: str, width: int = 16) -> str:
    try:
        return f"{float(value):{width}.4f}"
    except (TypeError, ValueError):
        return f"{'n/a':>{width}s}"


def render_result(data: dict) -> str:
    out: list[str] = []
    out.append(f"Run:      {data['simulation_run_id']}")
    out.append(f"Status:   {data['status']}")
    if data.get("change"):
        c = data["change"]
        out.append(f"Change:   {c['variable_id']} {c['change_type']} {c['change_value']} "
                   f"(route: {c['model_route']})")
    if data.get("baseline"):
        b = data["baseline"]
        out.append(f"Baseline: {b['name']} ({b['solve_start']}..{b['solve_end']})")
    if data.get("model_versions"):
        vs = ", ".join(f"{v['model']}={v['version']}" for v in data["model_versions"])
        out.append(f"Models:   {vs}")
    if data.get("error"):
        out.append("")
        out.append(f"ERROR [{data['error']['type']}]:")
        out.append(textwrap.indent(textwrap.fill(data["error"]["message"], 96), "  "))

    if data.get("tax_calculator_result"):
        t = data["tax_calculator_result"]
        out.append("")
        out.append(f"Tax-Calculator (year {t['tax_year']}, v{t['taxcalc_version']}):")
        out.append(f"  reform: {t['reform']}")
        out.append(f"  iitax:      base {_fmt(t['base_iitax'])} -> reform {_fmt(t['reform_iitax'])}")
        out.append(f"  payrolltax: base {_fmt(t['base_payrolltax'])} -> reform {_fmt(t['reform_payrolltax'])}")
    if data.get("tax_fair_adapter_result"):
        a = data["tax_fair_adapter_result"]
        out.append("")
        out.append(f"Tax-to-Fair adapter [{a['mapping_id']}]:")
        out.append(f"  {a['source_variable_id']} --{a['method']}--> "
                   f"{a['target_fair_variable']} {a['fair_change_type']} {a['derived_delta']}")
        out.append(f"  allocation: {a['quarterly_allocation_method']} x{len(a['quarterly_values'])} quarters")

    deltas = data.get("metric_deltas") or []
    if deltas:
        out.append("")
        out.append("Metric deltas (baseline vs changed):")
        header = (f"  {'METRIC':8s} {'PERIOD':8s} {'BASELINE':>16s} {'CHANGED':>16s} "
                  f"{'DELTA':>14s} {'DELTA%':>10s}  UNIT")
        out.append(header)
        for d in deltas:
            pct = d.get("percentage_delta")
            pct_s = f"{float(pct):10.4f}" if pct is not None else f"{'n/a':>10s}"
            out.append(
                f"  {d['metric']:8s} {d['period']:8s} {_fmt(d['baseline'])} "
                f"{_fmt(d['changed'])} {_fmt(d['absolute_delta'], 14)} {pct_s}  {d['unit']}"
            )
    if data.get("interpretation"):
        i = data["interpretation"]
        out.append("")
        out.append(f"Economic interpretation ({i['model_id']}, prompt {i['prompt_version']}):")
        for para in i["response_text"].split("\n\n"):
            out.append(textwrap.indent(textwrap.fill(para.strip(), 96), "  "))
            out.append("")
    return "\n".join(out).rstrip() + "\n"
