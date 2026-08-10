# Model Integration

## Ray Fair FP (primary macro model)

Vendored source: `FMFP/EngineFM/fp.for` (Fair-Parke Program, 2013-11-11);
US model defined in `FMFP/Definition/fminput.txt` (US MODEL JULY 31, 2026);
data in `FMFP/Data/{fmdata,fmexog,fmage}.txt`. **Vendored files are never
edited.**

### Build (`scripts/build_fair.sh`)

- gfortran from the repo-local micromamba env (`.mamba/envs/toolchain`).
- Mechanical patches applied to a **copy** in `build/fair/`:
  1. 7× `ACCESS='TRANSPARENT'` → `'STREAM'` (dead multicountry code).
  2. `RAN3` declared `REAL*8` + matching declaration in `RNORA` (historic
     link-time type mismatch; RAN3 feeds only stochastic paths).
- `GETCL` satisfied by `scripts/getcl_stub.f` (forces stdin-driven mode).
- Flags: `-std=legacy -ffixed-line-length-80 -fno-automatic
  -finit-local-zero -fno-range-check -fdollar-ok -O2`.
- conda-forge gfortran 16's macOS link specs are broken
  ("too many arguments to %:version-compare"): compile with gfortran `-c`,
  link with system clang against the env's `libgfortran`.
- Output: `data/artifacts/fair/bin/fp` (+ QUIT smoke test).

### Operating contract (all verified against the compiled binary)

- fp is driven via stdin; first prompt accepts `INPUT FILE=X ;` **or**
  `READJOB FILE=X ;` (READJOB works ONLY at this prompt, not inside a file).
- Filenames UPPERCASE, run inside a staged scratch dir
  (`data/runtime/fair/<name>/`, see `staging.py`).
- Base job (`scripts.build_base_job`): fminput.txt up to and including
  `SETYYTOY;`, then `WRITEJOB FILE=BASE.BIN;` + `SMPL` + machine-readable
  re-solve. Full base run (2SLS estimation + 2 solves) takes seconds.
- Scenario job: stdin `READJOB FILE=BASE.BIN ;` + `INPUT FILE=SCENBODY.TXT ;`
  where the body is `SMPL 2026.3 2029.4;` [+ `EXOGENOUS VARIABLE=RS;`] +
  CHANGEVAR block + SOLVE FILEWRITE + metric list + `QUIT;`.
- **CHANGEVAR input format** (line-oriented): `CHANGEVAR;` then
  `<VAR> <OP>` on one line, the numeric value on the NEXT line, then `;`.
  Ops: ABSOLUTE→ADDSAMEABS, PERCENT→ADDSAMEPCT (fraction, so user % / 100),
  SET_VALUE→SAMEVALUE.
- FILEWRITE output: per variable, an A8 name line then values 4-per-line
  (F19.10), 30 quarters (2022.3–2029.4); the 14 solve-window quarters are
  the trailing slice (parser slices from the end).
- Success = exit 0, no fatal strings, exactly 14 ` ITERS=` lines per solve.
- Fatal log patterns: `Solution error`, `ERROR IN RD`, `COMMAND PARAMETER
  NOT RECOGNIZED`, `Variable name not found`, `Command name … not found`.
  Benign (data load): `Name X not found.` followed by `Name added to list`.
- READJOB determinism verified: zero-change READJOB solve reproduces the
  base FILEWRITE output byte-identically (gate test in
  `test_real_models.py::test_readjob_determinism_gate`).
- RS is endogenous (Fed reaction function); scenario scripts emit
  `EXOGENOUS VARIABLE=RS;` (registry `requires_exogenous: true`), verified
  to hold RS exactly at base+delta.

## Tax-Calculator (conditional micro model)

Vendored PSL Tax-Calculator 6.7.3 in `taxcalc/` (CPS data bundled). Used via
the **library API only** ([runner.py](../app/infrastructure/taxcalc/runner.py)):

```python
pol = Policy(); pol.set_year(2026)          # current-law values for reform building
rec = Records.cps_constructor(gfactors=GrowFactors())   # ALWAYS pass gfactors
calc = Calculator(policy=pol, records=rec)  # deep-copies its inputs
calc.advance_to_year(2026); calc.calc_all()
calc.weighted_total("iitax" | "payrolltax" | "combined" | "c00100" | "expanded_income")
```

- Baseline and reform run sequentially (~1.5 GB peak); measured wall time
  ~16 s for the pair (numba JIT, works on Python 3.13).
- Reform dicts are built against current-law values (`reforms.py`), never
  hard-coded. Composite `II_rt_all` fans out to `II_rt1..7`.
- 6.7.3 has no `soi_iitax` switch → SECA buckets into payrolltax; recorded
  as `soi_iitax=False` with a caveat in adapter metadata.
- `NOTAXCALCJIT=1` disables numba JIT if debugging is needed.

## Tax-to-Fair adapter

Config: [config/tax_to_fair_mapping.yaml](../config/tax_to_fair_mapping.yaml);
code: [tax_to_fair.py](../app/infrastructure/adapters/tax_to_fair.py). Only
two methods exist, both grounded in the README ("feeds effective tax rate
parameters into the Fair Model"):

1. `EFFECTIVE_RATE_DELTA` → D1G: `(reform_iitax − base_iitax) / base_agi`.
   AGI (c00100) is the denominator because iitax/AGI is level-commensurate
   with Fair's D1G (~0.1155 at 2026Q2 in fmdata.txt). Measured example:
   II_rt_all −0.02 → ΔD1G ≈ −0.0132.
2. `STATUTORY_RATE_PASSTHROUGH`: FICA employee → ΔD4G, employer → ΔD5G
   (implied absolute statutory delta, computed reform-target − current-law).

Everything else (e.g. `CTC_c`) → `TaxToFairMappingError`, raised by
`ensure_mapping()` **before** the taxcalc run. Mappings are never guessed.
Quarterly allocation: constant delta across all 14 solve quarters, persisted.

## Baseline runbook

```
scripts/bootstrap.sh          # once: micromamba + gfortran + postgresql + pip deps
scripts/build_fair.sh         # once: compile fp
econ baseline-create          # full Fair base run → ACTIVE baseline in DB
```

Persists: `model_versions` (FAIR + TAX_CALCULATOR), `model_artifacts`
(BASE.BIN + 4 inputs + fp binary, sha256 each), `baselines` (ACTIVE; prior
actives retired), 140 `baseline_metrics` (10 metrics × 14 quarters).
BASE.BIN is archived under `data/artifacts/fair/<name>/`.
