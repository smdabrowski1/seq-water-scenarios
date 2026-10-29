# seq-water-scenarios

**[Live demo](https://seqwater.sebdabrowski.com)** · **[Walkthrough](https://sebdabrowski.com/seq-water)**

A scheduled data platform: ingests South East Queensland (SEQ) water data (BOM,
SILO, Seqwater), models it with dbt, pre-computes supply-demand scenarios, and
serves them through a live dashboard. Full brief: [SPEC.md](SPEC.md).

**The question this answers:** when does SEQ need its next major water supply
investment, and how much does that date move under different rainfall and
population assumptions?

## Status

All of the spec's 7-phase build plan (SPEC.md section 8) is built: ingest,
dbt modeling, the Polars scenario engine (`scenarios/`), and a FastAPI +
React dashboard (`backend/` + `frontend/`) serving it live - see the links
at the top of this README.

**What's real today:** `make refresh` runs the full pipeline end to end -
ingest → dbt seed/run into a temp DuckDB file → dbt test → validate → atomic
promote → registry flip. It pulls:

- **All 12 SEQ Water Grid dams' real daily storage** (%, ML) for the last ~5
  years, plus Seqwater's own precomputed grid-total series - scraped directly
  from `seqwater.com.au`'s server-rendered HTML (no headless browser needed;
  see `docs/decisions.md`).
- **Real full-supply-volume/capacity data** for all 12 dams, including the
  exact reduced-FSL notices (Somerset, Wivenhoe, North Pine, Lake Macdonald)
  the spec's "Reduced Full Supply Levels" trap (section 2) warns about.
- **~40 years of real daily rainfall** (`fct_dam_rainfall_daily`, 178,596 rows)
  at each dam's real coordinate (BOM gauge location or OpenStreetMap, per
  dam), from SILO's `DataDrillDataset` API - confirmed grid-based (5km cells,
  not true point interpolation) and confirmed to need no actual registration
  despite the spec's "free registration" framing. See `docs/decisions.md`.
- **Real reservoir boundary polygons for all 12 dams** (`dim_dam.geom_wkt`),
  fetched once from OpenStreetMap and committed as
  `reference/dam_boundaries.geojson` (visualization only, not used for any
  flow/hydrology modeling - see `docs/decisions.md`). OSM data is
  ODbL-licensed; attribution ("© OpenStreetMap contributors") is required
  wherever this geometry is displayed.

Earlier passes cross-checked Somerset against BOM's independent gauge data,
which caught a real discrepancy (BOM's Somerset % was stale against
Seqwater's own reduced-FSL reference) - documented in `docs/decisions.md`.
That cross-check source was removed once Seqwater was confirmed to cover all
12 dams directly: a separate ingest pipeline just to re-check one dam Seqwater
already covers stopped earning its keep. `ingest/bom_kiwis.py` stays in the
repo, unused, if a future cross-check is ever wanted again.

Query it directly:

```bash
uv run python -c "
import duckdb
con = duckdb.connect('data/warehouse.duckdb', read_only=True)
print(con.execute('select * from fct_grid_storage_daily order by storage_date desc limit 5').fetchall())
"
```

Or browse it in DuckDB's local UI:

```bash
uv run python -c "
import duckdb
con = duckdb.connect('data/warehouse.duckdb')
con.sql('INSTALL ui'); con.sql('LOAD ui'); con.sql('CALL start_ui()')
input('UI running - press enter to stop')
"
```

**What's still a gap:** The Seqwater historical series defaults to ~5 years,
not the full 2008+ range the source page's date picker allows - widening it
needs a Drupal AJAX form replay that hasn't succeeded yet (see
`docs/decisions.md`). Rainfall is scoped to ~40 years, not SILO's full 1889+
depth - a one-line change to widen later.

## Run it

```bash
uv sync
cp .env.example .env   # fill in SILO_API_KEY (free registration - see .env.example)
cp dbt/profiles.yml.example dbt/profiles.yml

make ingest    # fetches Seqwater (+ SILO if configured), lands raw parquet under data/raw/
make build     # dbt build: bronze -> silver -> gold, writes data/warehouse.duckdb directly
make refresh   # the real end-to-end pipeline: ingest -> dbt seed/run into a temp
               # DuckDB file -> dbt test -> validate -> atomic promote -> registry
               # flip. A failed run never touches data/warehouse.duckdb or
               # data/registry.db's current pointer - see warehouse/orchestrator.py.
make test      # pytest, including the pipeline_runs registry's start/activate/reap logic
make lint      # ruff check + format --check
```

To run the dashboard itself once the warehouse is built:

```bash
# backend
uv run uvicorn backend.main:app --reload --port 8010

# frontend (separate terminal)
cd frontend && npm install && npm run dev
```

Or build and run the whole thing as one container:

```bash
docker compose up --build   # http://localhost:8010
```

## Why GitHub Actions cron, not Airflow

A daily batch of this size - a handful of API calls plus one dbt build - doesn't
carry the backfill/DAG-dependency complexity that would justify running and
maintaining a scheduler. A single cron-triggered `make refresh` is the right amount
of machinery for what this pipeline actually does. See `docs/decisions.md` for the
full entry.

## Architecture

```
Seqwater pages ┐
SILO API       ┼─→ ingest/ (httpx + cache) ─→ raw parquet (data/raw/, partitioned by date)  [bronze]
               ┘                                    │
                                                     ▼
                         seeds/*.csv ──────→   dbt-duckdb project
                                             staging → intermediate  [silver]
                                                     │
                                                     ▼
                                               marts (dim/fct)        [gold]
                                            data/warehouse.duckdb
                                                     │
                                                     ▼
                                      scenario engine, Polars (scenarios/)
                                                     │
                                                     ▼
                                FastAPI (backend/) → React dashboard (frontend/)
```

`warehouse/registry.py` + `warehouse/orchestrator.py` implement the
write-temp → validate → promote pattern: a failed or interrupted run never
touches the warehouse file the dashboard reads from.
Every dbt layer materializes as a `table`, not the dbt-default `view` for
staging/intermediate - DuckDB bakes a view's catalog name (derived from the
file's own stem) into its stored SQL at creation time, which breaks after the
temp-file-to-final-path rename; tables don't carry that reference. See
`docs/decisions.md` for the real bug this was.

## Layout

- `ingest/` — one generic fetcher per source `kind` (`bom`, `silo`, `scrape`),
  dispatched from `ingest/config.py`'s `SOURCES` dict. `ingest/seqwater_scrape.py`
  is the primary source for the 12-dam grid (both the daily historical series
  and the FSL/current snapshot - real HTTP scraping of server-rendered HTML,
  no headless browser). `ingest/cache.py` is a persistent on-disk HTTP cache
  with hand-rolled retry/backoff.
- `warehouse/` — `registry.py` (SQLite `pipeline_runs` table: which run is
  current, its status, error, row counts) and `orchestrator.py` (the real
  ingest → dbt seed/run → dbt test → validate → promote pipeline).
- `dbt/` — dbt-duckdb project. `models/staging/` (bronze→silver: light typing,
  dam-name normalization), `models/intermediate/` (silver: per-dam and
  grid-total daily facts, gap-flagged), `models/marts/` (gold: `dim_dam`,
  `fct_dam_storage_daily`, `fct_grid_storage_daily`, `fct_dam_rainfall_daily`).
  Loads DuckDB's `spatial` extension (`dbt/profiles.yml`) for
  `stg_geo__dam_boundaries.sql`'s `st_read()` over the committed reference
  geometry. Custom data tests in `dbt/tests/` (day-over-day jump check,
  flood-range check on storage %, composite-uniqueness check on
  `fct_grid_storage_daily`) - warn/fail as appropriate, no `dbt_utils`
  dependency.
- `scenarios/` — Polars scenario engine: rainfall replay/climate adjustment
  (`climate.py`), demand projection (`demand.py`), analogue scenarios
  (`analogues.py`), and the water-balance model itself (`engine.py`). See
  `scenarios/LIMITATIONS.md` for what it doesn't model.
- `backend/` — FastAPI app serving the warehouse read-only to the dashboard.
- `frontend/` — React dashboard: observed dam/grid history and the
  scenario explorer (trajectory, supply-demand balance, investment toggles).
- `seeds/dam_grid_membership.csv` — deliberately small: only the facts that
  genuinely can't be scraped (BOM site-id crosswalk, catchment) plus the
  12-dam grid-membership categorization. Everything else about the dams
  (FSL, current/historical levels) comes from the automated Seqwater ingest,
  not a hand-maintained CSV.
- `reference/dam_boundaries.geojson` — real reservoir boundary polygons for
  all 12 dams, fetched once from OpenStreetMap (not a recurring ingest
  source - dam boundaries don't change day to day) and committed like a seed.
  Visualization only; ODbL-licensed, attribution required wherever displayed.
- `docs/decisions.md` / `docs/data-quality.md` — ADR-lite log and data-quality
  incident log, kept up to date as the project progresses - including the
  corrections logged when earlier conclusions turned out to be wrong.
