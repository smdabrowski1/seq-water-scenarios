# Scenario engine: limitations

Every item here is real and specific to this engine's actual construction,
not a generic disclaimer - each one was found and tested, not assumed. See
`docs/decisions.md`'s 2026-10-05 entries for the full investigation behind
several of these.

## The water-balance model

- **Calibrated on the SEQ Grid total, not per-dam geometry.** The first
  design (a single-catchment fit on Somerset, scaled to other dams by FSL
  volume) was built, tested, and failed genuine out-of-sample validation
  (R² = -0.04) - Somerset's level turns out to be substantially driven by
  operator decisions (flood mitigation, transfers with Wivenhoe), not
  rainfall. The model actually in use fits the Grid *total* against
  *regional* (all-12-catchment-average) rainfall - inter-dam transfers cancel
  out at the grid level by construction, and this does validate
  (leave-one-out cross-validated R² = 0.627). It cannot produce a per-dam
  breakdown, only a grid-wide trajectory.
- **The Grid's real calibration history is only ~5 years (2021-2026) and
  contains no drought.** The model validates well *within* that observed
  rainfall range (84.7-1,229.3 mm/quarter - see
  `int_grid_water_balance_coefficients`), but any scenario whose quarterly
  rainfall falls outside that range (most of the generic fan does, and the
  Millennium Drought Repeat scenarios certainly do) is genuine extrapolation
  beyond anything the model has been checked against. `fct_scenario_trajectory`
  carries `any_beyond_validated_range` for exactly this reason - check it
  before trusting a number at face value.
- **Linear, two-parameter, no antecedent-moisture memory.** Real hydrology
  treats antecedent soil moisture as a primary driver of rainfall-runoff
  nonlinearity; this model has no such state - each quarter's simulated
  change depends only on that quarter's own rainfall. Adding lagged rainfall
  terms was tried and didn't improve validation, so this is a real
  structural gap, not an unexplored fix.
- **The simulated "worst case" is bounded by 40 years of observed rainfall
  (1986-2025), not a true tail-risk estimate.** The Millennium Drought Repeat
  scenarios replay the worst drought *in our data* - if a more severe,
  unobserved multi-year sequence is physically possible, this engine has no
  way to generate or represent it (same limitation the climate-adjustment
  method has: it can't generate unprecedented events either).

## Demand

- **Demand is adjusted as a delta from a fixed real baseline, not an
  independent term.** The fitted `alpha` (the model's non-rainfall-driven
  change) already embeds whatever mix of real demand, evaporation, and
  operational release occurred during the 2021-2026 calibration window -
  there's no way to cleanly separate "how much of alpha was literally
  household demand" from the rest with the data available. Projecting a
  different demand scenario adjusts alpha by the delta from a fixed baseline
  (medium population, 160 L/day, averaged 2021-2026) and assumes the
  non-demand component (evaporation + typical release pattern) stays
  constant regardless of scenario. See `scenarios/engine.py`'s module
  docstring.
- **Per-capita demand figures are derived, not measured.**
  `seed_per_capita_demand`'s three tiers come from real Seqwater-published
  targets/triggers, but applying any one of them as a *constant* across a
  multi-year scenario is a simplification; real usage responds dynamically
  to restriction announcements, weather, and behaviour in ways a fixed L/day
  figure doesn't capture.
- **Demand growth isn't present anywhere in the historical rainfall
  record.** The water-balance model was fit on 2021-2026 storage behaviour
  under 2021-2026 demand; nothing in the fit itself "knows" about future
  population growth, which is why demand is projected and layered on
  separately rather than extrapolated from the fit.
- **Population projections (`seed_population_projections`) only extend to
  2046.** Any scenario whose balance-negative year would fall after 2046 is
  reported as `None` ("never crosses" within the data available) rather than
  a guess - this is a real horizon limit, not confidence the system is safe
  indefinitely beyond that year.

## Climate adjustment

- **Delta-change method**: scales observed historical rainfall by a fixed real percentage
  (`seed_climate_projections`), which preserves the historical sequencing of
  wet/dry periods and cannot generate a genuinely different (e.g. more
  front-loaded, or longer single dry spell) future pattern.
- **Climate figures are multi-model averages only, not ranges.** The source
  PDF (Queensland Government's 2024 SEQ regional climate summary) presents
  each figure as both an average and a shaded range across 15 climate
  models - only the average was extractable as plain text (the range is
  baked into the source's chart graphics). The engine therefore has no
  uncertainty band on the climate adjustment itself, only on the rainfall
  analogue fan.

## Supply side

- **Existing desal + recycled water (102 GL/yr) is treated as a fixed
  constant**, not a modelled trajectory with its own real constraints (plant
  maintenance windows, treatment capacity limits, desal ramping speed) -
  desal ramping changing drawdown isn't represented here. These two
  genuinely are the climate-independent sources (desal is seawater; recycled
  water's input is wastewater volume, tracking population more than
  rainfall).
- **Minjerribah (North Stradbroke Island) groundwater is NOT
  climate-independent** - it was originally lumped into the constant above,
  which was wrong. Seqwater's own North Stradbroke Island Drought Response
  Plan (seqwater.com.au/document/2261) monitors real aquifer bore-level
  drought triggers for this exact allocation, and a 2024 Redlands2030 report
  on the same aquifer states its level "hasn't even recovered" since the
  last drought. Its yield now varies year to year - a trailing 4-quarter
  average of the actual rainfall being replayed, scaled against the
  long-run historical average, floored at 20% of the sourced 16 GL/yr
  ceiling (an earlier version tied the decay to grid *storage* trigger
  tiers instead, the wrong basis - aquifer recharge responds to rainfall,
  not dam levels, and a flat scenario-wide figure didn't decay year to year
  at all). **The floor and the trailing-window length are a reasoned
  assumption, not a sourced figure** - no published GL/yr-vs-drought-severity
  curve exists for this specific Grid allocation; the Drought Response Plan
  gives response actions, not a yield number. Shown per-year in the
  dashboard's supply breakdown, labelled "modelled, rainfall-dependent."
- **The EMSV critical threshold uses 10%, the upper/safer bound of
  Seqwater's own stated 8-10% range**, not a single precise trigger point -
  a deliberate conservative choice, not the literal real trigger level.
- **Two of three future supply options' lead times are real but
  differently-sourced, and one remains unknown.** The second desalination
  plant's 5-year lead time comes from genuine industry precedent (cross-
  checked against three real Australian desal projects). The Logan River
  connection's 5-year figure is a derived estimate (a stated 2031 target
  year minus the 2026 as-at-date), not a duration Seqwater states directly -
  a meaningfully different kind of sourcing, flagged in
  `seed_supply_options`'s own notes column. The Gold Coast Desalination
  Plant capacity upgrade's lead time is genuinely unavailable
  (`TODO-VERIFY`) - no source gives it one, and none was guessed.

## What this means in practice

Every number this engine produces is traceable to a real source and a
tested (not assumed) model - but "traceable and tested" is not the same as
"precise." Treat `fct_scenario_trajectory`'s percentile bands as showing
*real uncertainty*, not a forecasting-grade confidence interval; treat
`fct_commit_by_dates`'s dates as planning-relevant signals ("this direction,
roughly this timeframe"), not dates a construction contract should be signed
against without further, more detailed engineering study.
