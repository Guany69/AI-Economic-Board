# Project Guide

## Why this project exists

This repository implements an MVP economic simulation system. A user submits an economic variable and a proposed change (delta); the system runs the appropriate economic-model workflow and returns the resulting economic consequences.

The High-Level Design (HLD) is the architectural source of truth. Do not redesign the system when implementing features. Low-level implementation details may evolve when needed, but HLD responsibilities, boundaries, control flow, persistence requirements, and model roles must remain intact.

## Architecture at a glance

The system uses four logical layers:

- **Presentation** — accepts the economic variable + delta, validates input shape, submits requests, and presents results.
- **Application** — the simulation orchestrator coordinates the workflow and assembles the final result.
- **Business Logic** — contains economic-change rules, model execution/evaluation logic, effect propagation, metric comparison, and consequence generation.
- **Data / Infrastructure** — provides model inputs/configuration, baseline data, persistence, model artifacts, and external integrations.

Model workflow:

- **Ray Fair is the master/primary macro model.**
- **Tax-Calculator is conditional** and runs only for supported tax-policy changes.
- Tax-policy changes flow through: `Tax-Calculator -> Tax-to-Fair adapter -> Ray Fair`.
- Changed Ray Fair metrics are compared with stored baseline/original metrics.
- The LLM runs only after deterministic model results and metric deltas exist; it interprets results and must not invent authoritative numerical outputs.

## Non-negotiable invariants

1. Every simulation begins with a user-requested economic variable + delta.
2. The application orchestrator coordinates the workflow; it should not absorb model-specific economics.
3. Normal simulations compare against stored baseline/original metric results.
4. Every changed macroeconomic scenario ultimately runs through Ray Fair.
5. Tax-Calculator runs only for applicable tax-policy changes.
6. Tax-Calculator output must be explicitly adapted before reaching Ray Fair.
7. Metric deltas are deterministic calculations, not LLM calculations.
8. The LLM interprets completed model results; it does not replace the economic models.
9. Simulation state and structured results are persisted in PostgreSQL.
10. Large raw model/data artifacts are referenced by metadata and are not stored wholesale in ordinary PostgreSQL tables.
11. Never invent economic equations, Ray Fair mappings, Tax-to-Fair transformations, model outputs, or missing data to make a feature appear complete. If a required mapping or artifact is unavailable, preserve the architecture and fail explicitly.

## How to work in this repository

Before making a meaningful change:

1. Inspect the relevant existing code and configuration.
2. Read the project documentation that applies to the task.
3. Preserve existing correct behavior unless the HLD requires it to change.
4. Prefer focused changes over broad rewrites.
5. Reuse existing abstractions when they already satisfy the architecture.
6. Keep model-specific code behind explicit adapters/interfaces.
7. Keep database access in the data/infrastructure boundary.
8. Keep presentation concerns out of business/model logic.
9. Add or update tests that prove the changed behavior.
10. Run the narrowest relevant verification first, then broader checks before finishing.

Do not claim implementation or tests are complete unless they were actually executed and verified.

## Progressive documentation

Read only the documents relevant to the current task:

- `agent_docs/hld_requirements.md` — complete HLD requirements and architectural traceability. Read before architecture changes, orchestration changes, model integration work, persistence changes, or end-to-end implementation.
- `agent_docs/lld.md` — recommended low-level design. Treat as guidance; preserve the HLD when deviating.
- `agent_docs/model_integration.md` — Ray Fair, Tax-Calculator, Tax-to-Fair mapping, artifacts, metrics, and baseline details.
- `agent_docs/database.md` — persistence model, state management, model/version provenance, and migrations.
- `agent_docs/testing.md` — test strategy, acceptance cases, and verification commands.
- `agent_docs/repository_map.md` — codebase map and ownership of major packages/components.

If a referenced document does not yet exist, do not invent its contents. Inspect the repository and available project sources, then create or request the missing documentation as appropriate.

## Source-of-truth order

When sources disagree, use this order:

1. HLD requirements
2. Explicit current task requirements
3. LLD guidance
4. Existing repository implementation

If the repository conflicts with the HLD, change the repository. If the LLD conflicts with the HLD, preserve the HLD and document the low-level deviation.

## Verification

Use the repository's existing deterministic tooling for formatting, linting, type checking, tests, migrations, and builds. Do not replace those tools with subjective manual checks.

For architecture-affecting work, finish by checking the relevant HLD requirements against the implementation and tests so no requirement was silently dropped.
