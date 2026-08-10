# HLD Requirements & Traceability

The HLD (see `Architecture.puml` / `UML.png`): a user submits an economic
variable + delta; the system runs the appropriate economic-model workflow and
returns the resulting consequences. Layers: Presentation → Application
(SimulationOrchestrator) → Business Logic → Data/Infrastructure.

## Workflow (normative)

1. User submits variable + delta → validated `EconomicChange`.
2. Orchestrator persists a PENDING run, then executes it (single worker).
3. Tax-policy changes (and only those) run Tax-Calculator, whose output is
   **explicitly adapted** (Tax-to-Fair adapter) into a Fair variable change.
4. **Every** changed scenario is solved by the Ray Fair model.
5. Changed metrics are compared against the **stored baseline** metrics;
   deltas are deterministic Decimal arithmetic.
6. Only after deterministic deltas exist does the LLM interpret them.
7. The assembled SimulationResult (change, versions, tax/adapter sections,
   metrics, deltas, interpretation, or error) is persisted and returned.

## Invariant traceability (CLAUDE.md invariants 1–11)

| # | Invariant | Implementation | Test |
|---|-----------|----------------|------|
| 1 | Every simulation begins with variable + delta | `POST /api/v1/simulations` requires `variable_id` + `change` ([routes.py](../app/presentation/api/routes.py)); `ChangeValidator` | `test_api.py` Case C tests |
| 2 | Orchestrator coordinates, holds no model economics | [orchestrator.py](../app/application/orchestrator.py) calls protocol interfaces only; economics live behind `MacroModelRunner`/`TaxModelRunner`/`TaxToFairAdapter` | `test_orchestrator.py` (runs with fakes — proves decoupling) |
| 3 | Comparison against stored baseline | `BaselineRepository.get_metrics` feeds `MetricComparisonService.compare`; the Fair scenario's in-run "base" is never used | `test_case_a_direct_fair_end_to_end` (deltas == fake offset) |
| 4 | Every scenario runs through Ray Fair | orchestrator always calls `fair_runner.run_scenario` (both routes) | Cases A + B tests assert `fair_runner.calls` |
| 5 | Tax-Calculator only for applicable tax changes | `ModelRoute` from registry; DIRECT_FAIR never touches `tax_runner` | Case A asserts `tax_runner.calls == []` |
| 6 | Tax output explicitly adapted before Fair | `ConfiguredTaxToFairAdapter.derive` → persisted `tax_fair_adapter_results` row → `FairChange` | Case B asserts adapter row + `fair_variable == "D1G"` |
| 7 | Metric deltas deterministic, never LLM | [comparison.py](../app/business/comparison.py) pure Decimal; LLM receives finished deltas | `test_comparison.py`; prompt forbids computation |
| 8 | LLM interprets only, after models | interpretation is the last step; `AnthropicInterpreter` system prompt v1 forbids inventing numbers | Case G asserts interpreter not called on Fair failure |
| 9 | State + results persisted in PostgreSQL | 12-table schema ([models.py](../app/infrastructure/persistence/models.py)), Alembic `0001` | `test_repositories.py`, migration applied in CI flow |
| 10 | Large artifacts by metadata only | `model_artifacts` stores path/sha256/size; BASE.BIN (7.4 MB) archived on disk | baseline-create verification |
| 11 | Never invent economics; fail explicitly | `TaxToFairMappingError` (CTC_c), `MissingApiKeyError`, `FairExecutionError`, registry-only variables | Cases C, D, E, F, G, H |

## Acceptance cases → tests

| Case | Meaning | Test |
|------|---------|------|
| A | Direct Fair change end-to-end; taxcalc does not run | `test_orchestrator.py::test_case_a…`, `test_api.py::test_case_a…`, real: `test_real_models.py::test_real_direct_fair_scenario` |
| B | Tax change: taxcalc → persist → adapter → persist → Fair → compare → LLM | `test_case_b…` (orchestrator + api), real: `test_real_taxcalc_effective_rate_plausibility` |
| C | Invalid variable rejected; no model runs | `test_case_c…` (422; validator units) |
| D | Missing baseline → safe failure; no model runs | `test_case_d…` (409; no PENDING row) |
| E | Tax-Calculator failure → FAILED; nothing fabricated | `test_case_e_taxcalc_failure` |
| F | Undefined mapping → FAILED before taxcalc/Fair | `test_case_f…` (orchestrator + api) |
| G | Fair failure → FAILED; LLM never invoked | `test_case_g…` |
| H | LLM failure → FAILED; deterministic results retained | `test_case_h…` (real `AnthropicInterpreter`, key unset) |

## State machine

`PENDING → RUNNING → COMPLETED | FAILED` (also `PENDING → FAILED`).
Enforced twice: policy map in [state.py](../app/domain/state.py) and a guarded
`UPDATE … WHERE status=:from` in `SimulationRunRepository.transition`.
Startup recovery: RUNNING → FAILED("interrupted"), PENDING re-enqueued.
