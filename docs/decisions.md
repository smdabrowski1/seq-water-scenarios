# Decisions

ADR-lite: one entry per non-obvious choice. Context, options, choice, consequence.
Three sentences each is plenty.

## 2026-09-28 — GitHub Actions cron over Airflow

**Context:** the pipeline needs a daily scheduled refresh (ingest -> dbt build ->
dbt test -> export -> publish).
**Options:** Airflow (or another DAG scheduler) vs. a single GitHub Actions cron job.
**Choice:** GitHub Actions cron.
**Consequence:** a daily batch of this size (a handful of API calls, one dbt build)
has no backfill/dependency-graph complexity that would justify a scheduler with its
own infrastructure to run and maintain - a cron trigger calling `make refresh` is the
right amount of machinery, not an under-engineered shortcut.

## 2026-09-28 — `pipeline_runs` registry: one row per run, not per dataset

**Context:** the Hobby CDM Project's `dataset_versions` registry keys rows by
`(name, version)` because it tracks N independently-versioned datasets.
**Options:** carry that two-dimensional key over vs. simplify since this project has
exactly one warehouse file.
**Choice:** simplify to one row per run (`run_id` as the sole key).
**Consequence:** `activate_run` only ever has one "current" row to flip, which is
simpler to reason about, but this registry can't (and doesn't need to) express
"dataset A is on version 3 while dataset B is on version 5" the way the sibling
project's does.

## 2026-09-28 — BOM KiWIS is HTTPS, not HTTP; SPEC.md's URL is stale

**Context:** SPEC.md section 3.1 lists the KiWIS base URL as
`http://www.bom.gov.au/waterdata/services`. A real request against that URL (via
`make ingest`) returned a `301 Moved Permanently` to the `https://` equivalent.
**Choice:** per this project's own stated rule ("where this spec and the live
source disagree, the live source wins"), `ingest/bom_kiwis.py`'s `BASE_URL` is
`https://...`, and `ingest/cache.py`'s httpx client sets `follow_redirects=True` so
any future redirect surfaces as a followed request rather than a swallowed 3xx.
**Consequence:** confirmed by hitting the live endpoint, not assumed from the spec text.

## 2026-09-28 — Confirmed real KiWIS response shapes (Phase 0 recon)

**Context:** ran `ingest/recon_bom.py` against the live endpoint (samples saved
under `docs/samples/`) rather than coding against remembered/assumed schemas.
**Observed:**
- `getSiteList` / `getTimeseriesList` both return `list[list[Any]]`: **a header
  row of column names, then data rows** — not a dict, and not a dict-per-row
  either. `getSiteList` header: `["site_name", "site_no", "site_id"]`.
  `getTimeseriesList` header: `["station_name", "station_no", "station_id",
  "ts_id", "ts_name", "parametertype_id", "parametertype_name"]`.
- `getTimeseriesValues` returns `list[dict]`, one dict per requested `ts_id`,
  shaped `{"ts_id", "rows", "columns", "data"}` where `data` is a list of
  `[timestamp, value, quality_code]` triples — this matches what
  `ingest/bom_kiwis.py`'s `fetch_timeseries` already assumed, confirmed rather
  than left as a guess.
- Both `station_no` and `site_no` work as the filter param name for
  `getTimeseriesList`.
**Consequence:** `ingest/bom_kiwis.py`'s `list_sites`/`list_timeseries` return
type hints fixed to `list[list[Any]]`; `ingest/cache.py`'s `get()` return type
loosened to `Any` since BOM never returns a dict at the top level.

## 2026-09-28 — SEQ grid dams not found under BOM Storage Volume/Level parameter types

**Context:** SPEC.md open question 1 asks whether all 12 SEQ Water Grid dams
have usable storage timeseries in BOM Water Data Online. Queried
`getSiteList` filtered to `parametertype_name=Storage Volume` (565 sites) and
`Storage Level` (633 sites) and searched both for every grid dam name
(Wivenhoe, Somerset, North Pine, Hinze, Baroon Pocket, Leslie Harrison, Ewen
Maddock, Cooloolabin, Sideling Creek, Lake Macdonald, Little Nerang, Wappa).
**Observed:** zero matches in either list. Both storage-parameter site lists are
dominated by SunWater-operated regional Queensland dams (Fairbairn, Burdekin
Falls, Paradise Dam, Wuruma, etc.) and dams in other states — not Seqwater's SEQ
Water Grid. Wivenhoe itself *does* have BOM gauges (`w00066-143026A` etc.), but
only under `Water Course Level`/`Water Course Discharge` parameter types (river
gauge, not dam storage).
**Consequence:** this is a real, unresolved gap, not something to paper over
with a fabricated station ID — `ingest/config.py`'s `bom_wivenhoe_level` entry
points at the real river gauge with a note that it is not a storage series.
Options to resolve, not yet attempted: (a) check whether BOM tracks these dams
under a different parameter type entirely (e.g. reservoir-specific codes not
covered by name search), (b) treat this as confirming SPEC.md 3.3's known gap
and rely on Seqwater's own site/dam-levels scrape plus a direct data request to
`communications@seqwater.com.au`, (c) search by BOM's internal dam codes rather
than English names if a crosswalk exists. Raised here rather than guessed at.

## 2026-09-28 — Correction: Somerset Dam *does* have real BOM storage data; the site-list-by-parametertype search method was unreliable

**Context:** the previous entry concluded no SEQ grid dam has storage data in
BOM, based on searching `getSiteList` filtered to `parametertype_name=Storage
Volume`/`Storage Level` for dam names. Querying `getTimeseriesList` directly
for each dam's known river-gauge `station_no` (rather than trusting the
site-list parameter filter as a complete index) told a different story.
**Observed:** `station_no=143305A` (Somerset, "Stanley_R Somerset") exposes 94
timeseries, including real `Storage Volume` and `Storage Level` series - e.g.
`ts_id=368803010` (`DMQaQc.Merged.DailyMean.24HR`, Storage Volume, ML) and
`ts_id=368784010` (same cadence, Storage Level, %). Pulled with `from=1996-01-01`:
**11,228 daily rows**, real values from 1996-05-22 through yesterday
(2026-09-26), 1,625 gap days (quality_code=-1, mostly pending/not-yet-published
recent days). Neither series appeared in the earlier Storage-Volume/Level
site-list search - that filter is evidently not a complete index of what
`getTimeseriesList` will actually return per station. The same direct check
for Wivenhoe (143026A), Hinze (146017A/146018A), and Baroon Pocket (138106A)
found no Storage Volume/Level series, and in fact *no populated series at all*
under any parameter/ts_id tried (all returned zero rows regardless of date
range) - those gauges appear dormant via this API, a separate finding from
"doesn't exist."
**Consequence:** `ingest/config.py` now has two real, live, working BOM
sources (`bom_somerset_storage_volume_ml`, `bom_somerset_storage_level_pct`).
The other 11 grid dams remain unresolved - 4 (Leslie Harrison, Ewen Maddock,
Cooloolabin, Sideling Creek, Wappa - and Sideling Creek/Wappa have zero BOM
presence under any name) have no BOM presence at all; the rest have gauges
that return no populated data via this API. `dbt/models/marts/fct_grid_storage_daily`
is built to carry only Somerset today, structured to extend by unioning in
more dams once/if their sources are confirmed - not a placeholder that fakes
a 12-dam grid total.

## 2026-09-28 — Seqwater dam-levels page is JS-rendered; dropped per spec's own contingency

**Context:** fetched `https://www.seqwater.com.au/dam-levels` directly (no
browser). SPEC.md open question 6 asks whether Seqwater's site permits
scraping and says to drop the source entirely if not.
**Observed:** the static HTML has no embedded dam-level data and no visible
JSON API endpoint - the page is a Drupal-rendered wizard/form
(`ajax_form=1` POST target visible in the markup) that populates data
client-side via JavaScript. Confirmed by grepping the raw response for dam
names/percentages: none present outside of unrelated intro prose.
**Choice:** per SPEC.md's own pre-authorized fallback, dropped as a live
source rather than adding a headless-browser dependency (e.g. Playwright) not
named in the approved stack. `ingest/seqwater_scrape.py` stays a documented
`NotImplementedError` stub, `optional: True` in `ingest/config.py` so it never
blocks a run.
**Consequence:** current-day Seqwater freshness (vs. BOM's own storage series,
which already covers Somerset) is not available; not revisited unless the
user decides a headless-browser dependency is worth adding.

## 2026-09-28 — dbt medallion architecture stood up on real Somerset data

**Context:** with two real BOM sources landing (`make ingest`), built the
staging -> intermediate -> marts layers per SPEC.md section 5's shape, scoped
to what's real today rather than the full 12-dam grid.
**Choice:** `dbt/models/staging/_sources.yml` maps each raw parquet partition
glob straight onto a dbt source via dbt-duckdb's `external_location` (no copy
step); `stg_bom__somerset_storage_{volume,level}` do light typing only;
`int_storage_daily` joins volume+level per day with a combined gap flag;
`dim_dam` (from `seeds/dam_metadata.csv`, all 12 grid dams, only Somerset's
`bom_site_id` confirmed) and `fct_grid_storage_daily` are the gold layer.
Two custom singular tests (no `dbt_utils` dependency, per the spec's
ask-before-adding-deps rule): a day-over-day storage-jump check
(warn-severity - a real flood release can legitimately move this much water)
and a flood-compartment range check on storage %.
**Consequence:** `dbt build --project-dir dbt --profiles-dir dbt` passes (27
PASS, 1 expected WARN: 78 real day-over-day jumps over 30 years, consistent
with known flood events). `data/warehouse.duckdb` is genuinely queryable -
e.g. `select * from fct_grid_storage_daily order by storage_date desc limit
5` returns Somerset at 96.9% / ~300,370 ML as of 2026-09-25.
**Gotcha found:** `dbt/profiles.yml`'s `path` resolves relative to the
invocation cwd (repo root, since Makefile targets pass `--project-dir dbt`),
not relative to `profiles.yml`'s own directory - `"../data/warehouse.duckdb"`
silently landed the file one level *above* the repo. Fixed to
`"data/warehouse.duckdb"`; documented inline in `profiles.yml.example` so it
isn't rediscovered the hard way again.

## 2026-09-28 — Wired `warehouse/orchestrator.py`'s dbt steps for real (no longer stubs)

**Context:** the orchestrator's `_run_dbt_build`/`_run_dbt_test`/`_validate_warehouse`
were `NotImplementedError` stubs written before any dbt model existed. Real
models now exist (previous entry), so `make refresh` should actually build and
promote a warehouse, not stop early.
**Choice:** `dbt/profiles.yml`'s `path` reads `DBT_DUCKDB_PATH` (env var, via
Jinja `env_var()`) with the real warehouse path as default; the orchestrator
sets that env var to the temp path before shelling out to `dbt seed`, `dbt run`,
then `dbt test` (kept as three separate subprocess calls, not one `dbt build`,
so the registry's `building`/`testing` status split reflects what's actually
happening). `_validate_warehouse` opens the temp file read-only and checks
`fct_grid_storage_daily` has rows - a dbt-test pass already validates model
logic, this is the file-level "did the build actually produce something
usable" check, mirroring the sibling project's "parquet opens and has rows"
convention.
**Gotcha found:** the temp file was originally named `.tmp-<run_id>.duckdb`
(leading dot, two dots) - dbt-duckdb derives its catalog name from the file
stem, and that naming broke the derivation (`Binder Error: Catalog
".tmp-<run_id>" does not exist!`). Renamed to `tmp_<run_id>.duckdb` (no
leading dot, single dot before the extension) and it works.
**Consequence:** `make refresh` now runs for real: ingests Somerset's live
data, builds+tests the full medallion pipeline into a temp DuckDB file, and
only on success promotes it to `data/warehouse.duckdb` and flips the registry.
Verified by deleting `data/registry.db`/`data/warehouse.duckdb` and re-running
from cold - registry ends with exactly one `active`/`is_current=1` row,
`fct_grid_storage_daily` is queryable with real data, and no `tmp_*.duckdb`
file is left behind.

## 2026-09-28 — Major correction: Seqwater's own page has real data for all 12 grid dams; earlier "JS-rendered, no data" claim was wrong

**Context:** asked directly "are there other sources for this data", which
prompted checking Seqwater's site properly instead of trusting the earlier
"JS-rendered, no embedded data" conclusion (see the "dropped per spec's own
contingency" entry above). That conclusion was reached by searching the raw
HTML for dam names/percentages and only inspecting the *first* match, which
happened to land in intro prose - the actual per-dam table further down the
page was never found because the search wasn't followed through.
**Observed:** `https://www.seqwater.com.au/dam-levels` server-renders a real
`<table class="dam-levels-table">` with **every one of the 12 SEQ Water Grid
dams** (plus 13 more Seqwater-operated dams): current volume (ML), full
supply volume (ML - the *current operating* FSL, already reflecting any
reduction in effect), % full, last-observation timestamp, and free-text
reduced-FSL notices for Somerset/Wivenhoe/North Pine/Lake Macdonald - exactly
the reduced-FSL trap SPEC.md section 2 warns about, now with real numbers and
dates attached. `https://www.seqwater.com.au/historic-dam-levels` goes
further: a `drupalSettings.seqw_dam_levels.historical` JSON blob inlined in
the page gives **daily** %/ML for all 25 dams *and* a precomputed "SEQ Water
Grid" aggregate (the actual headline metric), for the last ~5 years by
default (full range back to 2008-07-01 exists per the date picker's `min`
attribute, but widening to it requires replaying a Drupal AJAX form
submission - attempted, didn't return the wider dataset in the time
available; TODO-VERIFY as a follow-up, not blocking). None of this needs a
headless browser - `httpx` + stdlib `re`/`json` is enough.
**Consequence:** Seqwater, not BOM, is now the primary source for the 12-dam
grid. `ingest/seqwater_scrape.py` implements two real fetchers:
`fetch_dam_levels` (the historical series) and `fetch_current_snapshot` (the
FSL/current table); both are real automated ingest sources
(`seqwater_dam_levels_historical`, `seqwater_dam_fsl_snapshot`), not a seed -
`seeds/dam_grid_membership.csv` shrank to just the handful of facts that
genuinely can't be scraped (BOM site-id crosswalk, catchment, the 12-dam
grid-membership categorization itself).
**A real cross-source discrepancy fell out of this**: BOM's Somerset volume
and Seqwater's own Somerset volume agree to within ~0.01-0.2% for the same
date, but BOM's Somerset *percentage* is consistently ~17.5-17.8 points higher
than Seqwater's own (e.g. 96.9% vs 79.0% on 2026-09-25) - BOM's % is computed
against a reference capacity that was never updated to reflect Seqwater's own
reduced-FSL regime. `dbt/models/intermediate/int_somerset_cross_check.sql`
keeps this queryable rather than silently picking one source. BOM's Somerset
sources are kept as `optional: True` cross-checks in `ingest/config.py`, not
modeled as truth.
**Lesson, stated plainly:** the first pass concluded "no data" from an
insufficiently thorough search (one string match, not a scan for a table),
and that wrong conclusion stood until directly challenged. Worth naming since
it's exactly the kind of failure this project's own conventions (never
fabricate, verify before coding, log data-quality incidents) exist to catch -
the process caught it, but only because it was pushed on, not because the
first pass was careful enough on its own.

## 2026-09-28 — Real bug: dbt views broke after the temp-file rename; fixed by materializing everything as tables

**Context:** after standing up the new Seqwater-based models, ran `make
refresh` end to end and it reported success (21 pass, 2 expected warnings).
Manually querying `int_somerset_cross_check` afterwards failed:
`Binder Error: Catalog "tmp_20260928-134342" does not exist!`
**Root cause:** DuckDB derives a database's catalog name from the file's own
stem. dbt-duckdb bakes that catalog name into a VIEW's *stored* SQL text at
creation time (confirmed via `select sql from duckdb_views()` - every join
was fully qualified as `"tmp_<run_id>".main.<table>`). `warehouse/orchestrator.py`
builds into `tmp_<run_id>.duckdb` and `os.replace()`s it to `warehouse.duckdb`
once tests pass - the file's bytes move, but a view's stored definition still
says `tmp_<run_id>`, which no longer exists as a catalog after the rename.
Tables aren't affected (their committed rows carry no catalog-qualified SQL),
which is exactly why this passed `_validate_warehouse` - it only checked
`fct_grid_storage_daily`, a table, and every mart happened to be a table too.
**Choice:** `dbt/dbt_project.yml` now materializes staging and intermediate
as `table` instead of `view` (marts already were tables) - the only
materialization that survives the rename unconditionally, given this
project's write-temp-then-promote pattern. Also strengthened
`_validate_warehouse` to check one table from every layer (including
`int_somerset_cross_check`) instead of just the final mart, so this class of
bug can't hide behind an unrepresentative single check again.
**Consequence:** confirmed by rebuilding from a clean `data/` and querying
`int_somerset_cross_check` afterwards - works. The extra disk/build-time cost
of tables-over-views is negligible at this data size (tens of thousands of
rows, not millions).

## 2026-09-28 — Removed BOM's Somerset-only sources; Seqwater covers it directly now

**Context:** with Seqwater confirmed as a real, primary source for all 12
grid dams (including Somerset), a whole separate ingest pipeline just to
cross-check one dam Seqwater already covers stopped earning its keep.
**Choice:** removed `bom_somerset_storage_volume_ml`/`_level_pct` from
`ingest/config.py`, their staging models, and
`int_somerset_cross_check`. `ingest/bom_kiwis.py` itself stays (unused, not
deleted) in case a future cross-check against a source BOM covers well is
ever wanted.
**Consequence:** the one real finding this cross-check caught (BOM's
Somerset % is stale relative to Seqwater's own reduced-FSL reference; the two
sources' ML volumes agreed closely) doesn't need the source to keep running
to stay true - it's permanently on record in this file's earlier entry.
Removing the code doesn't un-discover the bug, it just stops paying an
ongoing cost to keep re-proving something already proven.
`warehouse/orchestrator.py`'s `_validate_warehouse` table list updated
(`int_somerset_cross_check` → `int_storage_daily`, so every layer is still
checked, not just the final marts). Rebuilt clean from a fresh `data/` -
18 pass, 2 expected warnings, unchanged from before the removal.

## 2026-09-30 — SILO's point API requires no real registration; landed 40 years of real rainfall

**Context:** SPEC.md 3.1 describes SILO as needing "free registration (email
used as key)". Checked SILO's own docs pages for any signup/registration
requirement - none found (searched all three key pages for "regist"/"sign
up"/"apply", zero hits). Confirmed directly: called the live
`DataDrillDataset.php` endpoint with a made-up email (`test@example.com`) and
it returned real data immediately, no signup step exists.
**Also confirmed, correcting an earlier claim in this file:** this is
fundamentally **grid-based data**, not point-based, despite being called the
"point API". Queried three coordinates within ~1km of each other (same 5km
grid cell) and got byte-identical rainfall values and elevation for all
three - the API doesn't interpolate to your exact coordinate, it snaps to a
grid cell and returns that cell's value. `DataDrillDataset` is a query
interface onto SILO's same underlying 5km spline/kriged grid that the bulk
NetCDF downloads also expose, not a distinct point-level product.
**Real dam coordinates sourced** (not fabricated) for all 12 grid dams: 5 from
BOM's own gauge records (`site_latitude`/`site_longitude` via
`getSiteList` - confirmed these fields exist and work, unlike the earlier
recon which never requested them), the remaining 7 from OpenStreetMap's
public Nominatim geocoder (results tagged `dam`/`reservoir`/`water` at the
named place, e.g. "Lake Macdonald Spillway" tagged `dam`).
**Choice:** `ingest/silo.py` rewritten to match the real, confirmed
`DataDrillDataset.php` contract (`start`/`finish`/`lat`/`lon`/`format`/
`username`/`password`/`comment`, not the guessed shape it had before). A real
email (`smdabrowski1@gmail.com`, with explicit permission) is used as
`username` even though it isn't checked, since there's no reason not to be
identifiable to an external service when asked. History scoped to ~40 years
(1986-present, covering the Millennium Drought and 2011/2022 floods) rather
than SILO's full 1889+ depth, for now - a one-line change (`HISTORY_START`)
to widen later.
**Consequence:** `fct_dam_rainfall_daily` - 178,596 real rows (12 dams x ~40
years), one grid-cell reading per dam (not an area-weighted catchment average
- explicitly documented as a stated simplification, see the source's own
description in `_sources.yml`). Spot-checked: Wivenhoe's annual rainfall
total is visibly lower through 2000-2007 (Millennium Drought years) than the
wetter years bookending it (1999: 1093mm, 2010: 1023mm) - a real, sane pattern.
**One real gap still open:** `source_code` (present in every row, e.g. `25`)
is landed but not interpreted - SILO's docs pages that should explain it
404'd during recon. Not guessed at; flagged TODO-VERIFY in the code.

## 2026-09-30 — Real bug: bronze partitions accumulating across days silently duplicated every downstream table

**Context:** after adding the rainfall source and rebuilding, `dbt test`
failed: `unique_dim_dam_dam_name` got exactly 12 duplicate results, and the
grid-storage uniqueness test got ~1825 duplicates - both suspiciously close
to "everything doubled."
**Root cause:** `seqwater_dam_fsl_snapshot` and `seqwater_dam_levels_historical`
are both **full refetches** every run (not incremental appends) - but this
project's convention (correctly) never deletes old `dt=` partitions, so once
a second day's capture existed on disk (an earlier session's `dt=2026-09-28`
alongside today's `dt=2026-09-30`), every staging model's `external_location`
glob (`dt=*/...parquet`) read *both* partitions' full contents as one table -
literally every row twice for the snapshot source, and every day's full
history twice for the levels source. `_validate_warehouse`'s row-count checks
didn't catch this (a table with 2x too many rows still has "rows").
**Choice:** every staging model reading a hive-partitioned `dt=` glob now
deduplicates to the most recent partition per business key
(`row_number() over (partition by <key> order by dt desc) = 1`) - confirmed
DuckDB auto-exposes `dt` as a real column from the folder name, no extra
plumbing needed. This is a general pattern, not a one-off fix: any bronze
source that's a full-history refetch (as opposed to a genuinely incremental
append) needs this in its staging model, or partition accumulation silently
duplicates it the next time more than one day's capture exists on disk.
**Consequence:** rebuilt clean - `unique_dim_dam_dam_name` and the grid
uniqueness test both pass now. This bug would have recurred for
`stg_silo__rainfall` too (also a full refetch) had it not been written with
the dedup logic from the start.

## 2026-09-30 — Dashboard built as live FastAPI + React + Docker, not the spec's static-site plan

**Context:** SPEC.md's Phase 4 calls for a static, pre-computed dashboard
(Evidence.dev or React+Vite+Observable Plot, data exported to JSON, hosted on
GitHub Pages, no runtime backend). Explicit direction this session: build it
instead as a live FastAPI + React + Docker stack mirroring the Hobby CDM
Project's own architecture, since the warehouse is small enough that live
DuckDB queries per request cost nothing, and this matches a stack already
proven to work well for this exact kind of app.
**Choice:** `backend/` (FastAPI, `backend/db.py`'s `Store` class mirrors the
sibling project's `engine.py` concurrency pattern - `self.con.cursor()` per
request, not the shared connection directly, since FastAPI's sync routes run
on a thread pool and a single DuckDB connection isn't safe for concurrent
`execute()` calls). `frontend/` (React + Vite + MapLibre GL + Observable
Plot). `Dockerfile` multi-stage (Node build → Python runtime, serving the
built frontend via `StaticFiles` same-origin - no CORS needed in Docker,
only in local dev where Vite's `:5173` and the API's `:8010` are different
origins). No tippecanoe/vector tiling - 12 polygons is nothing, raw GeoJSON
is fine (unlike the Hobby CDM Project's much larger polygon datasets).
**Port 8010, not 8000** - deliberately different from the Hobby CDM
Project's own port, confirmed necessary the hard way (a stray `curl` hit
that project's already-running Docker container on 8000 and returned its
health-check shape, not this project's).
**Three real bugs found via live browser testing** (Playwright, since no
Node/chromium-cli was available on this host - `uv run --with playwright`
instead), not caught by any automated check beforehand:
1. `Plot.barY` assumes a categorical (band) x-scale; this chart's x-scale is
   continuous (`utc`) - threw `scale incompatible with channel: utc !== band`,
   an uncaught error that unmounted the *entire* React tree (no Error
   Boundary existed yet) - this is what "the page appears then disappears"
   actually was. Fixed by switching to `Plot.areaY`/`Plot.lineY` (a thin area
   also reads better than discrete bars at ~1,829 days in a ~640px panel
   anyway - bars would be sub-pixel). Added `ChartErrorBoundary` so a future
   chart-specific bug can't repeat this blast radius.
2. The map's fixed center/zoom made the real reservoir polygons (small
   footprint relative to the whole SEQ region) look like tiny specks - not a
   bug exactly, but fixed by fitting the map to the real data bounds instead
   of a guessed viewport.
3. Observable Plot's tip mark sets `fill="var(--plot-background)"` as an
   inherited SVG presentation attribute - confirmed via `getComputedStyle`
   that this reliably resolved to white regardless of the actual
   `--plot-background` value (text's `currentColor` resolved correctly,
   only the balloon background didn't) - a plain white tooltip box against a
   dark page, functioning but unreadable/looked broken. Fixed with an
   explicit CSS rule targeting the tip's path directly
   (`.chart-panel svg g[aria-label="tip"] > g > path { fill: var(--surface-1) }`)
   rather than trusting the attribute's own var() resolution.
**Consequence:** verified end-to-end via Playwright in both light and dark
`color_scheme` - tooltips readable in both, map click and dropdown selection
both correctly sync state, a real historical event (the Feb 2022 SEQ floods)
visibly correlates between the storage and rainfall panels for Wivenhoe.
Added a date-range filter (90 days / 1 year / 2 years / all) per the
dataviz skill's interaction guidance (one row, above the charts, scoping
everything below it).

## TODO — Phase 0/2 items still open

- [ ] Widen `seqwater_dam_levels_historical` from the default ~5-year window
      to the full 2008-07-01+ range - the Drupal AJAX form replay didn't
      return the wider dataset in the time available; needs another attempt
      or a documented decision to accept the 5-year window as sufficient.
- [ ] `seeds/dam_grid_membership.csv`'s `bom_site_id`/`catchment` are
      TODO-VERIFY for 11 of 12 dams (only Somerset's `bom_site_id` confirmed).
      Given BOM's `getSiteList` does expose real lat/lon (discovered
      2026-09-30), it likely also has a cleaner way to crosswalk `site_no`
      for more dams than currently populated - not yet attempted.
- [ ] `fct_dam_rainfall_daily`'s `source_code` column meaning unconfirmed
      (SILO docs 404'd) - landed as-is, not interpreted.
- [ ] Current Drought Response Plan trigger percentages, current Water Security
      Program yield figures (SPEC.md open questions 3-5).
## 2026-09-30 — All 12 dam reservoir boundaries fetched (OpenStreetMap), committed as a static reference file

**Context:** wanted real reservoir polygon geometry for visualization
(explicitly not for flow/gradient hydrology modeling - see this file's
"gradient based water getting to the dam" discussion). First attempts via
Overpass API found 8 of 12 dams' polygons; the other 4 (Baroon Pocket,
Cooloolabin, Wappa, Little Nerang) came back empty even after retries across
three Overpass mirrors.
**Root cause of the 4 "misses":** not missing data - wrong search terms.
Baroon Pocket Dam's reservoir is actually named "**Lake Baroon**" in OSM (and
everywhere else - confirmed via web search), not "Baroon Pocket"; the BOM
gauge coordinate used for Little Nerang was apparently the wrong nearby
point (possibly an upstream stream gauge, not the dam itself) - searching by
the dam's own name instead ("Little Nerang Dam") found its real, distinct
polygon ~9km from where the BOM coordinate pointed. Cooloolabin and Wappa
were confirmed (independently, via web search, not just OSM) to genuinely
have no separate lake name - the earlier "no result" was correct, not a
naming miss.
**Method that actually worked for all 12:** Nominatim's `polygon_geojson=1`
parameter returns full boundary geometry directly in a plain search request -
no Overpass query-language wrangling, no mirror instability, one request per
dam. All 12 resolved on the first correctly-named attempt.
**Choice:** run-once, not a recurring ingest source - dam boundaries don't
change day to day, so re-fetching on every `make ingest` would be pointless
load on OSM's infrastructure for data that never changes. Fetched once,
written to `reference/dam_boundaries.geojson` (a GeoJSON FeatureCollection,
each feature carrying `dam_name`, the OSM way id, and the OSM display name
for provenance), and committed like a seed. `dbt/profiles.yml` now loads
DuckDB's `spatial` extension; `stg_geo__dam_boundaries.sql` reads the file
directly via `st_read()` (confirmed real column shape:
`dam_name`/`osm_type`/`osm_id`/`geom` - a native `GEOMETRY('EPSG:4326')`
column). `dim_dam` gained `geom_wkt` (via `st_astext()`, so downstream
consumers get portable WKT text, no ongoing spatial-extension dependency)
plus `geom_osm_type`/`geom_osm_id` for provenance.
**License note:** OSM data is ODbL-licensed - attribution ("(c) OpenStreetMap
contributors") is required wherever this geometry is displayed (e.g. the
eventual Phase 4 dashboard map). Recorded in the reference file's own
`metadata` block; needs to actually appear in the dashboard UI once built,
not just in this file.
**Consequence:** verified real - polygon sizes range from Lake Macdonald
(~5KB of WKT) to Wivenhoe (~268KB, the largest reservoir, as expected).
`dbt build` passes with the `spatial` extension loaded.

## 2026-10-02 — Phase 3 prep: sourced real population + climate seed data for the demand and climate-adjustment dimensions

**Population (`seeds/seed_population_projections.csv`):** QGSO's own
low/medium/high-series LGA workbook
(`qld-population-projections-regions-tables-lgas-qld-low-med-high-series-2021-2046.xlsx`,
2025 edition), downloaded directly and parsed with `openpyxl` - not transcribed
by hand. Three sheets (`Low series`/`Medium series`/`High series`), one row per
LGA, six year columns (**2021, 2026, 2031, 2036, 2041, 2046 - 5-year steps, not
annual**; the scenario engine will need to interpolate or just operate on this
native 5-year grid). Filtered to the 11 LGAs the SEQ Water Grid actually
supplies - 198 rows (11 × 3 series × 6 years), all present with no gaps.

**Real correction caught before it shipped:** first pass filtered by a
hand-remembered list that *included Toowoomba and omitted Noosa*. Verified
against Seqwater's own `seqwater.com.au/seq-water-grid` page (fetched live,
not assumed) before writing the seed - the authoritative 11 are Brisbane,
Gold Coast, Ipswich, Lockyer Valley, Logan, Moreton Bay, **Noosa**, Redland,
Scenic Rim, Somerset, Sunshine Coast. Toowoomba has its own separate water
supply system and is not part of the SEQ Water Grid retail area, despite
sometimes being discussed alongside it (there's a connected pipeline for
emergency supply only). Worth remembering next time this LGA list is needed
anywhere in the project - don't re-derive it from memory.

**Climate (`seeds/seed_climate_projections.csv`):** the Queensland Future
Climate Dashboard itself (`longpaddock.qld.gov.au/qld-future-climate/dashboard/`)
is interactive-map-export only - no bulk download or API, confirmed via its
own user guide. Used the Queensland Government's own pre-built regional
summary instead - "Climate change in the South East Queensland region"
(Version 2, 2024), a CC-BY-licensed PDF published by the Department of
Energy and Climate, built from the *same* underlying Queensland Future
Climate Science Program simulations. Extracted its real text with
`pdfplumber` (not OCR/guessed) and took the six annual-average-precipitation
multi-model-average figures: 2050 and 2090, crossed with the three CMIP6
SSP scenarios (SSP1-2.6 low / SSP2-4.5 medium / SSP3-7.0 high emissions),
relative to a 1981-2010 baseline.

**Known gap, recorded rather than silently dropped:** the source PDF presents
each figure as a multi-model-**average** (a vertical line) *and* a shaded
range across all 15 climate models (a horizontal bar) - only the average
was extractable as plain text; the range is baked into the PDF's chart
graphics, not a text/table value, so it isn't in the seed. If the scenario
engine ever needs an uncertainty band on the climate adjustment (not just a
point estimate), that range needs sourcing from the Dashboard's own
shapefile/data-table export instead - flagged, not fabricated.

**Non-obvious, don't "fix" it:** the figures are *not* monotonic in emissions
severity at the 2050 time slice - SSP1-2.6 (low emissions) shows the
*largest* rainfall decline (-5.2%) while SSP3-7.0 (high emissions) shows the
smallest (-2.3%); by 2090 the ordering is different again (SSP2-4.5 largest
at -6.9%, SSP1-2.6 smallest at -6.3%). This is exactly what the published
source states, not a transcription error - rainfall response is far more
model-uncertain than temperature response in these projections (the source
PDF says this explicitly: "large uncertainty in the magnitude of projected
changes in rainfall"). Scenario engine should carry these numbers as-given,
not smooth them into a tidier-looking monotonic trend.

**Still open:** `seed_per_capita_demand.csv` (litres/person/day assumptions)
is still a derive-and-document task, not sourced from either of these two
downloads - per SPEC.md 3.2 this one is supposed to be derived, with the
derivation documented, not pulled from an external publisher.

## 2026-10-04 — `seed_per_capita_demand.csv` and `seed_supply_options.csv` built from real, directly-sourced Seqwater figures

**Per-capita demand:** researched UK vs Australia consumption as a sanity
check before settling on Australian (SEQ-specific) numbers - UK national
average is 136.5 L/person/day (Environment Agency, 2024-25), genuinely close
to SEQ's, not an order of magnitude apart as initially assumed. Also caught
and corrected a wrong claim along the way: the UK/EU "population equivalent"
standard is 60g BOD/day (EU Urban Waste Water Treatment Directive), not 80g -
80g is the *US* convention. Doesn't affect this seed directly (BOD load isn't
a drinking-water demand figure) but worth not leaving uncorrected.

Landed on three scenario variants, each tied to a real, named Seqwater
mechanism rather than an evenly-spaced guess:
- **status_quo (160 L/day)**: recent observed regional average. Weakest
  sourcing of the three - confirmed only via a search-result snippet of a
  real Seqwater page (`news/weekly-water-security-and-consumption-update`);
  direct fetch of that page returned HTTP 403 (bot protection) on every
  attempt. Flagged in the seed's own `notes` column rather than silently
  presented as equally solid as the other two rows.
- **efficiency (150 L/day)**: Seqwater's own voluntary/pre-drought
  conservation messaging target - directly fetched and confirmed (a 2021
  news article: actual usage of 151 L/day was "one litre shy" of this
  target).
- **drought_restricted (140 L/day)**: the real, *enforced* Medium Level Water
  Restrictions target, legally applied by the SEQ Retailer Customers once
  combined Grid storage drops to 50% - directly fetched and confirmed from
  Seqwater's own 2023 Water Security Program (p.33).

**Real correction mid-research:** the first draft of this three-tier set
conflated two different Seqwater numbers - the 150 L/day *voluntary* target
and the 140 L/day *enforced* Medium Level Restrictions trigger - as though
they were the same mechanism at different severities, which produced a
non-monotonic (and wrong) ordering. Re-reading Seqwater's own Water Security
Program directly (Figure 10, "Drought response triggers") separated them
into their real distinct phases: pre-drought (voluntary, 70-50% storage) vs.
drought-declared (enforced, 50-25% storage). A fourth, more severe EMSV tier
(100 L/day, enforced at 8-10% storage, p.34) exists in the same source if a
4th scenario variant is ever wanted - not included here since SPEC.md 6.3
asks for "two or three" variants.

**Supply options:** split into `existing` (dams, groundwater, desal, PRW -
already operating, each with a real yield figure from the Water Security
Program's p.9 source table) vs `future` (second desal plant, GCDP capacity
upgrade, Logan River/Wyaralong connection - real named projects from the
same document, p.7/p.27, but genuinely not given a yield/lead-time/capex
figure in the source text). `TODO-VERIFY` used throughout for the `future`
rows' numeric columns rather than inventing a plausible-looking number -
per SPEC.md 9's "never fabricate a figure" rule. One mix-up avoided
deliberately: Borumba Pumped Hydro (also mentioned in the same source
document, p.27) is an *energy storage* project by Queensland Hydro, not a
water supply option, despite sharing the Lake Borumba name with an existing
Seqwater dam - not included in this seed.

**Still open:** confirming whether BOM Water Data Online has usable storage
history for any of the 11 non-Somerset grid dams - API has been returning a
real, persistent 503 outage across every attempt this session (not a
search-method problem this time). Re-searching the full cached 202,648-row
site list (rather than the unreliable parametertype-filtered one) did find
two untested candidate stations worth live-checking once the outage clears:
North Pine (`142102A`, literally named "N Pine_R Dam Site") and Little Nerang
(`146009A`) - neither was tried in the original Phase 0 recon. Wivenhoe
(`143026A`), Hinze (`146017A`/`146018A`) and Baroon Pocket (`138106A`) were
tested once before and got a "no populated series" verdict - worth a second
look given Somerset's own history (an identical single-check method missed
Somerset's real 11,228-row series the first time). Leslie Harrison, Ewen
Maddock, Cooloolabin, Sideling Creek and Wappa were searched far more broadly
this time (by real catchment/creek name, not just the dam name) and still
turned up nothing plausible - a stronger negative than the original check,
though not provable as complete without the live API back.

## 2026-10-05 — The water-balance model's first design (Somerset, local rainfall) failed real out-of-sample validation; the one that actually works fits the Grid total instead

**Context:** Phase 3's rainfall-replay method (SPEC.md 6.1) needs a way to turn
a rainfall sequence into a storage trajectory. The first design fit a linear
regression (`change_ml = alpha + beta * trailing_rainfall_mm`) on Somerset's
real BOM history (1996-2026, the only dam with drought-era storage data - see
above), scaled to the other 11 dams by FSL volume. A **daily** version of this
fit came back at R^2 ~ 0.0006 - no real explanatory power, and `beta` had the
physically wrong sign (negative: more rain predicting *less* storage gain).

**First fix attempt - aggregate to smooth out noise.** Daily data looked
dominated by operational releases/transfers (Somerset and Wivenhoe are
flood-mitigation-operated and water-shared - single-day swings of several
hundred ML with no matching rainfall event). Tested weekly/monthly/quarterly
aggregation: weekly R^2=0.025, monthly R^2=0.029, **quarterly R^2=0.157** (the
ceiling - lag terms, tested explicitly, didn't improve on same-quarter
rainfall: previous-quarter alone R^2=0.006, a 2-quarter sum R^2=0.102, both
worse than same-quarter's 0.157). Sign corrected at quarterly grain (beta
positive, alpha negative) - a real improvement, but still weak.

**The real test that mattered: out-of-sample, not in-sample.** Fit on
Somerset's first 72 quarters (1996-2014), predicted the held-out last 32
(2014-2026): **out-of-sample R^2 = -0.04** - worse than just guessing the test
period's mean. The in-sample 15.7% was optimistic noise from a small sample
(104 points), not a generalizable relationship. Durbin-Watson on the
quarterly residuals came back ~1.98 (no real autocorrelation) - ruling out
"missing antecedent-moisture memory term" as the fix, consistent with lagged
rainfall not helping above. Heteroscedasticity was confirmed present
(residual variance scales with rainfall level) - another violated OLS
assumption.

**Two more approaches tested, same honest out-of-sample methodology, both
still failed:**
- k-nearest-neighbour analog matching (real historical Somerset quarters with
  similar rainfall, average their real observed change) instead of a
  parametric fit - consistent with SPEC.md 6.1's own "analogues, not a fitted
  model" philosophy. Best case (k=10): R^2=0.062; k=1/3/5 all strongly
  negative, k=15 ~ zero. Inconsistent, not a real fix - confirms the problem
  is the *signal*, not the model family.
- Regional rainfall (averaged across all 12 catchments) instead of Somerset's
  own local point rainfall, on the theory that a region-wide signal might
  explain Somerset's grid-managed behaviour better than local rain. In-sample
  R^2 actually improved (26.5%) but out-of-sample got *worse* (-0.29) - a
  textbook overfitting pattern, not a fix.

**Root cause, now well-evidenced rather than guessed:** Somerset's quarterly
storage change is not reliably explained by rainfall - by any of three
genuinely different methods tried. The most likely real explanation is that
Somerset's level is substantially driven by deliberate operator decisions
(flood mitigation, transfers with Wivenhoe - already visible in the daily
data's volatility pattern), not passive catchment hydrology. No amount of
rainfall-signal engineering fixes that, because rainfall was never the
dominant driver for this specific dam.

**What actually works: the SEQ Grid *total* against regional rainfall.**
Inter-dam transfers (Wivenhoe <-> Somerset, etc.) net to zero at the grid
level by construction - moving water between two grid dams doesn't change
the grid total. Fit on the Grid's real ~5-year history (19 quarters, only
data available - see below for the tradeoff this trades in):
**in-sample R^2 = 0.728, leave-one-out cross-validated R^2 = 0.627** (LOOCV
used instead of a train/test split - 19 points is too few to split
meaningfully). This is a real, validated, substantially-explained
relationship - not comparable to any of the Somerset attempts.

**The honest remaining limitation, and it's a different one than before:**
the Grid's real history is only ~5 years and contains no drought - the model
validates well *within* the observed rainfall range (84.7mm to 1,229.3mm per
quarter, both bounds now stored as columns on
`int_grid_water_balance_coefficients` for exactly this purpose), but applying
it to Millennium-Drought-severity rainfall deficits is genuine extrapolation
beyond anything it's been checked against. This needs to be flagged
prominently in the scenario engine's output for any scenario whose rainfall
falls outside that observed range, not quoted as if the 62.7% CV figure
covers every case - decided explicitly with the user rather than silently
picking an approach.

**Architecture consequence:** `int_storage_change_weekly.sql` and
`int_dam_water_balance_coefficients.sql` (the Somerset-based, per-dam-FSL-
scaled design) were deleted, replaced by `int_grid_water_balance_coefficients.sql`
(grid-total grain, no per-dam scaling needed at all - a real simplification,
not just a swap). `scenarios/analogues.py` will now replay one grid-total
trajectory per historical start-year, not 12 summed per-dam trajectories.
`stg_bom__somerset_storage.sql` and its ingest source are kept, unused by the
model - still real, genuinely-sourced data (the only dam-level record
spanning the actual drought), useful for plausibility-checking scenario
output even though it isn't what gets fit.

## 2026-10-05 — Sourced real lead-time figures for 2 of 3 future supply options, closing the gap that was blocking commit-by dates

**Context:** running the full engine end-to-end (safe yield -> balance-negative
year -> commit-by date) against a real stressed scenario (high population,
2090 SSP3-7.0 climate adjustment, Millennium Drought Repeat fan) produced a
genuine finite balance-negative year (2043) - but every commit-by date came
back `None`, because the three *future* supply options (the ones a commit-by
date is actually for) all had `TODO-VERIFY` lead times. The spec's own stated
deliverable ("the commit-by date... is the actual number a planner would act
on") was unreachable for every option that mattered.

**Second desalination plant - lead_time_years now 5, sourced from two
independent real figures, not invented:**
1. Industry-level: Australian desalination projects are described in
   published sources as needing "a five year time frame from initial
   consideration to final commissioning" - cross-checked against three real
   precedents (Sydney Desalination Plant ~3yr construction, Hunter Water
   Belmont ~4yr construction, Melbourne's plant ~5yr announcement-to-
   completion).
2. Direct precedent: the Gold Coast Desalination Plant's own real history -
   initial 55ML/day proposal in 2005, expanded scope in 2006, construction
   began November 2006, first supplied the Grid February 2009, full capacity
   January 2009. Initial-consideration-to-full-operation ~= 4 years.
   Both land on ~4-5 years independently - used 5 as the slightly more
   conservative of the two.

**Logan River connection via Wyaralong Dam - lead_time_years now 5, but a
different kind of figure, flagged as such in the seed's own notes column:**
this project is already underway, not a hypothetical future decision - the
South West Pipeline segment completed in 2024, and Seqwater's own modelling
(a real Queensland Government ministerial statement, not the Water Security
Program PDF this time) states the remaining piece - the Wyaralong Water
Treatment Plant - "is likely to be needed around 2031," with contractors
already shortlisted. 5 years is this project's own derived estimate (2031
target minus the 2026 as-at-date), not a duration Seqwater states directly -
a meaningfully different kind of sourcing than the second desal plant's
figure, and the seed's `notes` column says so rather than presenting both at
equal confidence.

**Still genuinely unavailable, left TODO-VERIFY rather than guessed:** the
Gold Coast Desalination Plant capacity *upgrade* (distinct from the new
second plant) - no source found gives it a separate lead-time figure, and
inferring one from the new-build precedent above would be a real guess
(an upgrade to existing infrastructure is plausibly faster, but "plausibly"
isn't a source).

**Consequence:** re-running the same stressed scenario after landing this
seed update should now produce real commit-by dates for the second
desalination plant and the Logan River connection - the engine's actual
payoff, not just a balance-negative year with no action attached to it.

## 2026-10-05 — Phase 3 scenario engine built end-to-end: 9 named scenarios, 5 new marts, wired into `make refresh`

**Context:** with the validated Grid-total water-balance model in place (see
the two entries above), built out the rest of SPEC.md section 6: climate
adjustment, demand projection, safe-yield/balance-negative-year/commit-by-date
logic, named scenario config, and the dbt marts layer to make it queryable.

**New Python modules** (`scenarios/`): `climate.py` (scales a rainfall series
by a sourced `seed_climate_projections` %, per spec 6.2's "scale rainfall,
not storage"), `demand.py` (linearly interpolates `seed_population_projections`'
5-year steps to annual, sums across the 11 LGAs, multiplies by per-capita
L/day), `analogues.py` (the historical replay itself - `simulate_trajectory`
is the one-quarter-at-a-time water-balance step, `build_analogue_fan` runs it
for every historical start-year with a full window on record), `engine.py`
(`find_safe_yield` - binary search for the max constant demand that never
crosses the EMSV critical threshold across every analogue in a fan, same
concept real water utilities' IQQM-style modelling calls "system yield";
`find_balance_negative_year`; `compute_commit_by_dates`), `run_all.py` (the
orchestration script - reads the warehouse, runs every scenario in
`scenarios/config/scenarios.yml`, lands 5 parquet outputs via the same
write-temp-then-`os.replace()` pattern as `ingest/run_all.py`).

**9 curated scenarios, not the full 3x3x3 cross-product** (confirmed with the
user): baseline, optimistic, high_growth, climate_stressed_2050,
climate_stressed_2090, millennium_drought_repeat (real 1997-2009 window, not
3 years - see the entry above for why), millennium_drought_repeat_climate_adjusted,
best_case, and millennium_drought_repeat_unrestricted (added after running
the first 8 real: none of them crossed balance-negative, because the
Millennium Drought scenarios correctly use drought-restricted demand - which
is *realistic* but meant the engine's actual payoff, a real commit-by date,
never appeared anywhere in the curated set. The 9th scenario - same
climate/population stress, status-quo instead of restricted demand -
represents "restrictions aren't successfully imposed/complied with," and is
what actually produces a finite result: balance-negative year 2045,
commit-by 2040 for both the second desalination plant and the Logan River
connection. The contrast between scenarios 7 and 9 is itself a real,
useful finding about how much of the system's resilience depends on
restrictions actually working, not just existing on paper).

**5 new dbt marts** (`dim_scenario`, `fct_scenario_trajectory`,
`fct_supply_demand_balance`, `fct_commit_by_dates`, `fct_trigger_crossings`) -
one more than SPEC.md's section 5 literally lists. Deviation, reasoned: the
spec describes "the trigger date for each supply option" as a column on
`fct_supply_demand_balance` (scenario x year grain) - but a commit-by date
has grain (scenario, option), not (scenario, year); forcing it into that
table would mean repeating the same option's commit-by date on every year's
row. Split into its own `fct_commit_by_dates` mart instead - noted here, not
silently diverged from.

**`fct_scenario_trajectory` did not end up unioning with
`fct_grid_storage_daily`** despite that table's own `series` column being
explicitly designed for exactly this (see the 2026-09-30 entry). Real reason:
the two are genuinely different shapes - percentile bands (p10/p50/p90) and
quarterly grain vs. a single observed daily value - forcing a union would
need nullable band columns on the observed-history table for no benefit.
`fct_grid_storage_daily`'s `series` column stays single-valued
('observed') - resolved, not still-pending (the schema.yml TODO comment
about this has been updated to reflect the final decision).

**Two-pass dbt build, a real architecture requirement, not a choice**: the
scenario marts' sources are parquet files `scenarios/run_all.py` writes -
which itself reads from the *first* dbt build's output (`dim_dam`,
`fct_dam_rainfall_daily`, `int_grid_water_balance_coefficients`, the 5 input
seeds). Chicken-and-egg, solved by tagging all 10 scenario-dependent models
(5 staging + 5 marts) with `{{ config(tags=["scenario_output"]) }}`:
`warehouse/orchestrator.py` now runs `dbt run --exclude tag:scenario_output`
first, then `scenarios/run_all.py`, then `dbt run --select tag:scenario_output`,
then the full `dbt test` suite (registry gets a new `scenario_engine` status
between "building" and "testing" - no schema change needed, `status` is a
free-text column with no enum constraint).

**Also fixed in passing:** `seed_population_projections`, `seed_climate_projections`,
`seed_per_capita_demand`, and `seed_supply_options` never got schema tests
added when they were built (2026-10-02/04) - a real gap against
`seeds/README.md`'s own stated convention. Added `source_url`/`as_at_date`
not_null tests (plus `unique` where the natural key supports it) for all
four while touching `_schema.yml` for the new marts.

**Consequence:** `make refresh` now runs the complete pipeline - ingest, dbt
build, scenario engine, scenario marts, test, promote - in one command.
68-70 tests passing depending on run (the same 2 pre-existing warnings every
run this session has had, unrelated to today's work). 22 unit tests added
(`tests/test_scenarios.py`) covering the water-balance simulation step,
regional rainfall aggregation, analogue replay (including the
beyond-validated-range flag and the insufficient-data error path), demand
interpolation, climate adjustment (including its real-data-match error
path), and the full safe-yield/balance/commit-by chain on synthetic data.
Mandatory limitations section written to `scenarios/LIMITATIONS.md` per
SPEC.md 6's closing paragraph, naming every real simplifying assumption made
this session rather than leaving them implicit in code comments alone.
