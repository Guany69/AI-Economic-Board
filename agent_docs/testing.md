# Testing

## Tiers

| Tier | Path | Needs | What it proves |
|------|------|-------|----------------|
| unit | `tests/unit/` | nothing external | state machine, registry/loaders, validation/routing, Fair script golden files, FILEWRITE parser fixtures, comparison Decimal math |
| integration | `tests/integration/` | embedded PostgreSQL | repositories + guarded transitions, orchestrator Cases A–H with fakes, worker FIFO + orphan recovery |
| end-to-end | `tests/end_to_end/test_api.py` | embedded PostgreSQL | HTTP API → worker → DB with fakes; Case H uses the REAL AnthropicInterpreter with the key unset |
| real models | `tests/end_to_end/test_real_models.py` (`-m real_models`) | fp binary + taxcalc deps | full base run, **READJOB determinism gate**, real COG/RS scenarios, real taxcalc + adapter plausibility band |

## Commands

```
python3 -m pytest tests/unit tests/integration tests/end_to_end   # fast suite (Cases A–H)
python3 -m pytest -m real_models                                  # slow, real models (~1 min)
```

DB-dependent tests auto-skip when no PostgreSQL is reachable. Real-model
tests auto-skip when `data/artifacts/fair/bin/fp` is missing.

## Fakes

`tests/fakes.py`: `FakeFairRunner` (baseline+offset metrics or forced
failure), `FakeTaxRunner` (fixed aggregates → derived D1G delta −0.005),
`FakeInterpreter` (canned text, forced failure, or MissingApiKeyError).
They implement the domain protocols, so the orchestrator under test is the
production orchestrator.

## Acceptance mapping

See the Case A–H table in [hld_requirements.md](hld_requirements.md).

## Live verification (manual)

```
econ serve                                                # terminal 1
econ variables
econ simulate COG --type ABSOLUTE --value 25 --wait       # direct Fair
econ simulate II_rt_all --type ABSOLUTE --value=-0.02 --wait   # tax path
econ simulate CTC_c --type ABSOLUTE --value 500 --wait    # explicit mapping failure
```

Without `ANTHROPIC_API_KEY`, runs finish FAILED at `MissingApiKeyError`
with all deterministic sections populated (HLD Case H). With a key they
finish COMPLETED with the interpretation section.
