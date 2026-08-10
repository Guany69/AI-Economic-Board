# Low-Level Design

## Layering (dependency direction enforced)

presentation → application → business → domain; infrastructure implements
domain `Protocol`s ([interfaces.py](../app/domain/interfaces.py)) and is
injected via [`AppContext`](../app/application/context.py). Business and
domain code import no frameworks, no SQLAlchemy, no model libraries.

```
app/
  domain/           enums, entities (frozen dataclasses, Decimal), errors,
                    state machine, registry types, protocols
  business/         ChangeValidator, ChangeRouter (+CHANGEVAR op map),
                    MetricComparisonService (pure Decimal)
  application/      SimulationOrchestrator, SimulationWorker (1 daemon
                    thread + queue.Queue, strict FIFO), AppContext
  infrastructure/
    persistence/    db.py (embedded Postgres bootstrap), models.py (ORM),
                    repositories.py (all SQL; guarded state UPDATE)
    fair/           staging, scripts (pure text), runner (subprocess),
                    parser (FILEWRITE), periods, service (MacroModelRunner),
                    baseline (builder)
    taxcalc/        reforms (reform-dict builder), runner (TaxModelRunner)
    adapters/       tax_to_fair (TaxToFairAdapter)
    llm/            prompts (v1, deterministic render), client (Anthropic)
    artifacts/      store (sha256 describe/archive; metadata only)
  presentation/
    api/            FastAPI app, lifespan (migrations, recovery, worker)
    cli/            econ CLI (argparse + httpx over the API)
```

## Orchestrator transaction boundaries

No model executes inside an open DB transaction:

- TX1 (submit): PENDING run + economic_change.
- TX2: PENDING→RUNNING + model-version links.
- Tax route only: `ensure_mapping` (no TX) → taxcalc run → TX3a tax results
  → `derive` → TX3b adapter result.
- Fair scenario run → TX4 simulation_metrics.
- Comparison (read baseline TX, pure compute) → TX5 metric_deltas.
- LLM interpret → TX6 interpretation + RUNNING→COMPLETED.
- Any exception → single failure TX (`fail_from_any_active`); committed
  work from earlier TXs is retained (that's what Case H relies on).

## Config

- `config/economic_variables.yaml` — variable registry (single authority).
- `config/metrics.yaml` — 10 output metrics + units.
- `config/tax_to_fair_mapping.yaml` — the only tax→Fair conversions.
- Settings via pydantic-settings, env prefix `ECON_*`
  ([settings.py](../app/config/settings.py)); notable: `ECON_DATABASE_URL`
  (or plain `DATABASE_URL`), `ECON_FP_BINARY`, `ECON_LLM_MODEL`
  (default `claude-opus-5`), `ECON_FAIR_TIMEOUT_SECONDS`,
  `ECON_TAXCALC_TIMEOUT_SECONDS`.

## Numerics

Metric values are Decimal end to end; DB columns NUMERIC(24,10); percentage
deltas quantized to 10 dp and NULL when baseline == 0. Model outputs enter
as Decimal at the parser (`Decimal(token)` from fp text output) and at the
taxcalc boundary (`Decimal(repr(float))`).

## Known deviations from the original plan (HLD intact)

- `pgserver` pip package has no Python 3.13 wheel → embedded PostgreSQL is
  provided by the micromamba toolchain env instead (initdb/pg_ctl on a unix
  socket, managed by [db.py](../app/infrastructure/persistence/db.py));
  `DATABASE_URL` still overrides.
- Schema is 12 tables (the run↔version link table counted separately).
