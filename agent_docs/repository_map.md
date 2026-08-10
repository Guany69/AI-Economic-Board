# Repository Map

| Path | Ownership | Notes |
|------|-----------|-------|
| `FMFP/` | **vendored, read-only** | Fair-Parke Fortran source + US model definition + data. Never edit; build patches apply to a copy in `build/fair/`. |
| `taxcalc/` | **vendored, read-only** | PSL Tax-Calculator 6.7.3 (CPS data bundled). Library API only. |
| `tax/` | vendored aux | Tax-Calculator repo extras (docs etc.); not imported. |
| `app/` | application code | See [lld.md](lld.md) for the layer map. |
| `config/` | configuration | Variable registry, metric catalog, tax→Fair mappings. |
| `migrations/` | Alembic | `versions/0001_initial_schema.py`. |
| `scripts/` | tooling | `bootstrap.sh` (micromamba toolchain + deps), `build_fair.sh` (fp build), `getcl_stub.f`. |
| `tests/` | tests | unit / integration / end_to_end (+ `-m real_models`). |
| `agent_docs/` | docs | This documentation set. |
| `data/` | **generated, gitignored** | `artifacts/fair/bin/fp`, baseline archives (BASE.BIN), `runtime/fair/<run>/` scratch dirs (retained on failure), `pgdata/` embedded cluster. |
| `build/` | generated, gitignored | Patched fp.for copy + compile logs. |
| `.mamba/` | generated, gitignored | micromamba root: gfortran + postgresql toolchain env. |
| `Architecture.puml`, `UML.png` | HLD diagram | Source of truth for the flow. |
| `CLAUDE.md` | project rules | Invariants + progressive-documentation index. |

Entry points: `econ` console script → [cli/main.py](../app/presentation/cli/main.py);
API app → `app.presentation.api.main:app`.
