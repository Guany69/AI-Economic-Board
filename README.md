# AI Economic Board

A simulation and analysis platform that models the economic outcomes of policy changes — and works in reverse to identify what policies could achieve a target economic outcome.

## What It Does

Users choose one of two modes:

**Policy → Outcome:** Input a change to an economic policy (e.g., increase federal spending by $50B, cut the income tax rate by 2pp). The simulation runs with that change in place and returns updated economic metrics. The AI Counsel then interprets the results — explaining tradeoffs, second-order effects, and what changed and why.

**Outcome → Policy:** Input a desired (or undesired) economic outcome (e.g., reduce unemployment to 3.5%, lower inflation). The AI Counsel deliberates on which policy levers to adjust, selects a combination, runs the simulation, and then evaluates whether the outcome was achieved.

## The AI Counsel

The core of the platform is a multi-agent AI system structured as an economic advisory board. Each agent holds a distinct analytical role:

| Role | Domain |
|------|--------|
| Macroeconomic & Monetary Economist | Growth, inflation, unemployment, demand, investment, interest rates, Fed response |
| Fiscal & Debt Economist | Revenue, spending, deficit, debt, financing, interest costs, long-run budget effects |
| Household & Distribution Economist | Taxes, transfers, after-tax income, poverty, inequality, winners and losers |
| Labor, Industry & Regional Economist | Employment, wages, occupations, industries, supply chains, geographic effects |
| Evidence & Implementation Chair | Administrative feasibility, uncertainty, evidence quality, contradictions, final synthesis |

The board acts as consultant; the economic models provide the quantitative analytics.

## Economic Models

### Ray Fair Model (Primary Simulation Engine)

A large-scale macroeconometric model of the US economy. It tracks hundreds of variables across households, firms, governments, banks, and the foreign sector — estimated from decades of quarterly data. Policy inputs are translated into Fair Model variable changes; the model is then solved to produce updated economic trajectories.

**Controllable policy inputs:**

| Category | Variables |
|----------|-----------|
| Government spending | COG (federal purchases), COS (state & local purchases) |
| Household taxation | D1G (federal income tax rate), D1S (state & local income tax rate) |
| Corporate taxation | D2G (federal profit tax rate), D2S (state & local profit tax rate) |
| Payroll & Social Security | D4G (employee SS rate), D5G (employer SS rate) |
| Transfers to households | TRGHQ (federal transfers), TRSHQ (state & local transfers) |
| Federal grants to states | TRGSQ |
| Monetary policy | RS (Treasury bill rate — model-determined or user-overridden) |
| Tariff policy | CUST (customs duties, translated from a user-entered tariff rate) |
| Government employment | JG (federal civilian jobs), JS (state & local jobs), JM (military jobs) |
| Subsidies | SUBG (federal), SUBS (state & local) |

**Key output metrics include:** GDP, GNP, unemployment rate (UR), inflation (PCGDPD), disposable income (YD), interest rates (RS, RB, RM), household wealth (AA), federal deficit/surplus (SGP), and dozens more.

### Tax Calculator (TaxCalc)

Microsimulation model applied to a representative sample of US tax-filing units. Computes the distributional revenue effects of proposed federal income and payroll tax reforms under current law vs. the proposed change. Feeds effective tax rate parameters into the Fair Model.

### BEA Input-Output Model

Describes inter-industry purchase and sale relationships across the US economy. Useful for tracing where in the economy a policy's effects land — e.g., a $100B infrastructure program generating construction, steel, machinery, engineering, and transportation demand ripples through the supply chain.

### GDPNow

Atlanta Fed's real-time GDP nowcast. Used to calibrate the starting economic baseline to current conditions before running simulations.

### Planned / Future Models

- **CBO Small-Scale Policy Model** — combines short-run demand effects with long-run supply effects; useful as a cross-check on Fair Model results
- **FRB/US** — Federal Reserve Board's macroeconometric model; adds forward-looking expectations, financial markets, and monetary policy transmission; targeted for later integration

## Architecture Overview

```
User Input
    │
    ├─► Policy Change ──► Fair Model Simulation ──► Output Metrics
    │                                                      │
    │                                              AI Counsel Analysis
    │                                              (5-agent board)
    │
    └─► Target Outcome ──► AI Counsel Deliberation
                                    │
                               Policy Selection
                                    │
                           Fair Model Simulation
                                    │
                           Counsel Verification
```

Supporting analytics feed the Counsel:
- TaxCalc → revenue and distributional effects of tax changes
- BEA I-O → sectoral and supply-chain impacts
- GDPNow → baseline calibration

## Status

Active development. Core simulation loop and AI Counsel architecture are in design; Fair Model integration is the primary near-term milestone.
