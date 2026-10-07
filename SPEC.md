# SEQ Water Supply–Demand Scenario Platform — Build Spec

> This file is the brief for an AI coding agent. Read it fully before writing code.
> Treat every URL and figure here as *unverified until you fetch it*. Where this spec
> and the live source disagree, the live source wins — and note the discrepancy in
> `docs/decisions.md`.

---

## 1. What we are building and why

A scheduled data platform that ingests South East Queensland (SEQ) water data, models
it with dbt, pre-computes supply–demand scenarios, and serves them through a static
dashboard.

**The single question the dashboard answers:**

> When does SEQ need its next major water supply investment, and how much does that
> date move under different rainfall and population assumptions?

This mirrors a UK Water Resources Management Plan (supply yield vs demand growth, with
commit-by dates for each option), rebuilt on Australian public data. Seqwater's own
planning indicates grid enhancements are likely required within the next decade.

**Non-goals.** This is not a forecasting competition. Scenarios must be transparent,
reproducible and defensible, not accurate. No black-box ML on the headline numbers.
Do not build a flood model. Do not build user auth.

**Success criteria.**
- `make refresh` runs the whole pipeline end to end from a cold clone
- A GitHub Actions cron refreshes data daily and republishes the site with no manual step
- Every number on the dashboard traces back to a dbt model, and every dbt model to a documented source
- `dbt test` passes, and at least one test is a custom business rule, not just `not_null`
- A reader can find, in the README, exactly which inputs are live and which are hand-keyed

---

## 2. Domain primer (needed to model this correctly)

- **Seqwater** is the bulk water supplier. It owns the dams and treatment plants.
- The **SEQ Water Grid** connects the major drinking water dams — Wivenhoe, Somerset,
  North Pine, Hinze, Baroon Pocket, Leslie Harrison, Ewen Maddock, Cooloolabin,
  Sideling Creek, Lake Macdonald, Little Nerang, Wappa — so supply can be shifted
  between regions. **Grid storage %** is the headline planning metric, not any single dam.
- **Distributor-retailers** deliver to customers: Urban Utilities (Brisbane, Ipswich),
  Unitywater (Moreton Bay, Sunshine Coast), City of Gold Coast, Logan, Redland.
  Their demand forecasts drive Seqwater's planning.
- **Climate-independent sources**: the Gold Coast Desalination Plant (Tugun), and the
  Western Corridor Recycled Water Scheme (Bundamba, Luggage Point, Gibson Island),
  held as a drought response measure.
- **Drought Response Plan triggers** change operating posture as grid storage falls
  (roughly: restrictions start, then desal runs continuously, then purified recycled
  water is called on). **Verify the exact percentages from the current plan — do not
  trust remembered numbers. Put them in a seed file with a source URL and an as-at date.**

**Two modelling traps to handle explicitly:**

1. **Reduced Full Supply Levels.** Wivenhoe, Somerset and North Pine have operated at
   reduced FSLs during dam improvement works (North Pine's reduced FSL equates to about
   54% of nominal capacity). A raw "% full" is therefore **not comparable across years**.
   Model storage in **megalitres (ML)** as the canonical unit and derive percentages
   against an explicit, dated FSL reference. This distinction is a core part of the
   project's credibility.
2. **Flood compartments.** Wivenhoe and other gated dams hold flood storage above the
   water supply FSL, so readings above 100% are a flood-operations state, not surplus
   drinking water. Exclude flood compartment volume from supply calculations.

---

## 3. Data sources

### 3.1 Live pipeline sources (fetched on a schedule)

| Source | Gives | Access | Notes |
| --- | --- | --- | --- |
| **BOM Water Data Online** — `http://www.bom.gov.au/waterdata/` | Storage volume + storage level timeseries per site; streamflow | Kisters **KiWIS** API at `http://www.bom.gov.au/waterdata/services`, no API key | Primary historical dam source. Discover with `getSiteList` / `getTimeseriesList`, pull with `getTimeseriesValues`. Consider the `kiwis-pie` Python package, or plain `requests`. |
| **SILO** (Qld Dept of Environment / Long Paddock) — `https://www.longpaddock.qld.gov.au/silo/` | Daily rainfall + evaporation, 1889→yesterday, gap-filled, point or 5 km grid | Point API (free registration, email used as key); gridded NetCDF/GeoTIFF on AWS S3 | Primary rainfall source. Model-ready and gap-filled. **SILO warns it is not suitable for climate-change detection studies** — use it for catchment history, never to claim a trend. |
| **Seqwater dam levels** — `https://www.seqwater.com.au/dam-levels` | Current % full per grid dam | HTML scrape | Nice-to-have for "as at today" freshness. Check terms before relying on it; keep it non-essential so the pipeline survives a layout change. |

### 3.2 Seed sources (versioned CSV in `seeds/`, hand-keyed or one-off download)

| Seed | Gives | Where from |
| --- | --- | --- |
| `seed_dams.csv` | Dam name, BOM site ID, nominal FSL volume (ML), current reduced FSL + effective date, catchment, grid membership | Seqwater dam pages + BOM site list |
| `seed_drought_triggers.csv` | Grid storage % thresholds and the response at each | Seqwater Drought Response Plan (PDF) |
| `seed_supply_options.csv` | Option name, yield (ML/yr), lead time (years), indicative capex, status | Seqwater Water Security Program (PDF) |
| `seed_population_projections.csv` | Low/medium/high projected population by LGA to 2046 | Queensland Government Statistician's Office (QGSO) |
| `seed_climate_projections.csv` | Rainfall change % by time slice and emissions scenario for SEQ basins | Queensland Future Climate Dashboard (shapefile/PDF export) |
| `seed_per_capita_demand.csv` | Assumed litres/person/day, with scenario variants | Derived — **document the derivation** |

**Every seed row carries `source_url` and `as_at_date` columns. No exceptions.**

### 3.3 Known gaps — do not invent data to fill these

- **Seqwater historical dam levels**: no API, no bulk download, not on `data.qld.gov.au`.
  Seqwater directs requests to `communications@seqwater.com.au`. Backfill from BOM
  Water Data Online instead. (Sebastian may email them in parallel; if a file arrives,
  it lands in `seeds/` with provenance.)
- **Retailer demand time series**: not published. Demand must be *derived* as
  population × per-capita litres/day. Surface this on the dashboard as a stated
  assumption, not a fact.
- **Desal and recycled water production**: annual totals only in annual reports; no daily series.
- **Per-dam inflow/release**: patchy. Prefer deriving net change in storage over
  claiming measured inflow.

---

## 4. Architecture

```
  BOM KiWIS API ─┐
  SILO API ──────┼─→ Python ingest (httpx) ─→ raw parquet (data/raw/, partitioned by date)
  Seqwater page ─┘                                    │
                                                      ▼
                          seeds/*.csv ──────→   DuckDB file (data/seq.duckdb)
                                                      │
                                                      ▼
                                               dbt-duckdb project
                                          staging → intermediate → marts
                                                      │
                                                      ▼
                                         scenario engine (Python, Polars)
                                          writes marts_scenario_* tables
                                                      │
                                                      ▼
                                    export to JSON/Parquet (site/data/)
                                                      │
                                                      ▼
                                       static dashboard (Evidence or React)
                                                      │
                                              GitHub Pages
```

**Stack decisions (follow these unless you hit a blocker — then record it):**

- **Python 3.12**, dependency management with **uv**
- **DuckDB** as the warehouse — single file, no server, commits nothing binary to git
- **dbt-core + dbt-duckdb** for transformation, testing and docs
- **Polars** for the scenario engine (fast, and matches the author's existing stack)
- **httpx** for API calls, with retries and a persistent on-disk response cache
- **GitHub Actions** as the orchestrator — cron, not Airflow. Justify this in the README:
  a daily batch of this size does not warrant a scheduler, and saying so demonstrates
  better judgement than over-engineering.
- **Evidence.dev** for the dashboard *if* it renders the scenario fan chart acceptably;
  otherwise a small **React + Vite + Observable Plot** app. Decide in Phase 4, not now.
- Site hosted on **GitHub Pages**, data pre-computed — no runtime backend.

**Repo layout:**

```
seq-water-scenarios/
├── README.md
├── SPEC.md                  ← this file
├── Makefile                 ← refresh, test, build, serve
├── pyproject.toml
├── ingest/
│   ├── bom_kiwis.py
│   ├── silo.py
│   ├── seqwater_scrape.py
│   └── cache.py
├── seeds/                   ← versioned CSVs with provenance columns
├── dbt/
│   ├── dbt_project.yml
│   ├── models/{staging,intermediate,marts}/
│   └── tests/
├── scenarios/
│   ├── engine.py
│   ├── analogues.py
│   ├── demand.py
│   └── config/scenarios.yml
├── site/
├── docs/
│   ├── decisions.md         ← ADR-lite, one entry per non-obvious choice
│   └── data-quality.md      ← incidents found and how they were handled
└── .github/workflows/refresh.yml
```

---

## 5. Data model (dbt)

**Staging** (`stg_`) — one model per source, light typing and renaming only:
`stg_bom__storage`, `stg_silo__rainfall`, `stg_seqwater__dam_levels`, plus `stg_seed__*`.

**Intermediate** (`int_`):
- `int_storage_daily` — dam × day, volume ML, FSL-adjusted % full, gap-flagged
- `int_grid_storage_daily` — grid total ML and %, the headline series
- `int_catchment_rainfall_daily` — catchment × day, area-weighted from SILO points
- `int_storage_change_daily` — net daily change in ML, decomposed into the part
  explainable by rainfall and the residual (a proxy for draw + release + evaporation)

**Marts** (`fct_` / `dim_`):
- `dim_dam`, `dim_date`, `dim_scenario`
- `fct_grid_storage_daily` — the observed history
- `fct_supply_demand_balance` — year × scenario: available yield, projected demand,
  surplus/deficit, and the trigger date for each supply option
- `fct_scenario_trajectory` — scenario × date: projected grid storage path, with
  percentile bands from the rainfall analogues
- `fct_trigger_crossings` — scenario × trigger: probability and expected date of crossing

**Tests — at minimum:**
- Generic: `unique` + `not_null` on all keys, `accepted_values` on scenario names,
  `relationships` from facts to dims
- **Freshness**: fail if the latest storage date is more than 3 days old
- **Custom business tests** (these are what an interviewer will look at):
  - grid storage in ML never exceeds sum of FSL volumes for the same date's FSL regime
  - no dam has a day-over-day volume change exceeding a physically plausible bound
    without a corresponding rainfall event (flag, don't fail)
  - scenario demand is monotonically non-decreasing under the high-population scenario
  - every seed row has a non-null `source_url` and `as_at_date`

---

## 6. Scenario engine

Three independent dimensions, combined into named scenarios in `scenarios.yml`.

**6.1 Rainfall — historical analogues, not a fitted model.**
Take the observed rainfall sequence from each historical year (1889→present, via SILO),
replay it forward from today's actual starting storage, and produce a fan of
trajectories. This handles seasonality for free, needs no training, and every path is
explainable as "what if the next 3 years repeated 1999–2001". Report percentile bands
across analogues, not a single line.

**6.2 Climate adjustment.**
Apply a rainfall scaling factor from the Queensland Future Climate projections
(by time slice and emissions scenario) to the analogue sequences. Scale rainfall, then
recompute runoff — do not scale storage directly. Use at minimum a low-emissions and a
high-emissions variant, and be explicit that this is a delta-change method with known
limitations (it preserves historical sequencing and cannot generate unprecedented events).

**6.3 Demand.**
`demand_ML_per_year = population(LGA, year, series) × per_capita_L_per_day × 365 / 1e6`
summed across SEQ LGAs. Three population series (low/medium/high from QGSO) crossed with
two or three per-capita assumptions (status quo, efficiency improvement, drought-restricted).

**6.4 Output.**
For each scenario: the storage trajectory fan, the year the supply–demand balance turns
negative, and the **commit-by date** for each supply option (balance-negative year minus
that option's lead time). The commit-by date is the actual deliverable — it is the
number a planner would act on.

**Mandatory: a documented limitations section.** Demand growth is not in the historical
record; desal ramping changes drawdown; past wet seasons may not represent the current
climate; per-capita demand is derived, not measured. Name these before anyone asks.

---

## 7. Dashboard

Four views, pre-computed, no runtime queries:

1. **Now** — grid storage % and ML, per-dam breakdown, position relative to drought
   triggers, days since last significant inflow, data freshness stamp
2. **History** — grid storage since records began, with trigger bands and the millennium
   drought and 2011/2022 flood periods marked; rainfall deficit vs long-run median
3. **Scenarios** — the trajectory fan with trigger bands, scenario selector, probability
   of crossing each trigger within 1/3/5 years
4. **Supply–demand balance** — the WRMP-style chart: declining yield vs demand growth
   envelope, with option commit-by dates marked. **This is the money shot — design the
   rest around it.**

Every view carries a visible "as at" date and a link to the source. An "Assumptions"
panel is always one click away.

---

## 8. Build phases

| Phase | Deliverable | Done when |
| --- | --- | --- |
| **0. Recon** | `docs/decisions.md` started; API access confirmed | You have pulled one real timeseries from BOM KiWIS and one from SILO, and written down the actual response shapes |
| **1. Ingest** | `ingest/` with caching + retries; raw parquet landing | A cold `make ingest` populates `data/raw/` and is idempotent on re-run |
| **2. Model** | dbt staging → marts, all tests passing | `dbt build` green; `dbt docs generate` produces a lineage graph |
| **3. Scenarios** | `scenarios/engine.py` producing `fct_scenario_trajectory` and `fct_supply_demand_balance` | At least 6 named scenarios resolve, and commit-by dates fall out |
| **4. Dashboard** | Static site, four views | Builds from pre-computed JSON with no backend |
| **5. Automate** | `.github/workflows/refresh.yml` | Daily cron refreshes data, runs tests, republishes; a failing test blocks publish |
| **6. Write up** | README + `docs/data-quality.md` | A stranger can understand what is live, what is assumed, and what broke along the way |

Phases 0–2 are the ones that must be excellent. If time runs short, cut scenario count
and dashboard polish, never testing or documentation.

---

## 9. Conventions for the agent

- **Verify before coding.** Fetch each API once and inspect the real response before
  writing a parser. Do not code against remembered schemas.
- **Small commits**, one concern each, conventional commit messages.
- **Record every non-obvious decision** in `docs/decisions.md`: context, options, choice,
  consequence. Three sentences each is plenty.
- **Log data-quality incidents** in `docs/data-quality.md` as you hit them — a schema
  change, a duplicate load, a gauge with missing days. These are portfolio assets, not
  embarrassments. Do not silently patch them.
- **Never fabricate a figure.** If a number is needed and not available, put it in a seed
  with a `TODO-VERIFY` marker in `source_url` and raise it in the phase summary.
- **No secrets in the repo.** SILO key via env var / GitHub secret.
- Type hints on all Python; `ruff` for lint and format; `pytest` for ingest and engine logic.
- Ask before adding any dependency not named in section 4.

---

## 10. Open questions to resolve in Phase 0

1. Do all 12 grid dams have usable storage timeseries in BOM Water Data Online, or only
   the major ones? If coverage is partial, does grid total need reconstructing from a subset?
2. What is the actual historical depth available per dam via KiWIS?
3. What are the *current* Drought Response Plan trigger percentages, and the current
   published yield figures from the latest Water Security Program?
4. Does the Queensland Future Climate Dashboard export give per-basin rainfall deltas in
   a form that can be joined to catchments, or is manual transcription needed?
5. What is a defensible per-capita demand starting figure for SEQ, and what is its source?
6. Does Seqwater's site permit scraping? If not, drop 3.1 row three entirely — the
   pipeline must not depend on it.
