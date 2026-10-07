# Data quality

Incidents found and how they were handled - portfolio assets, not embarrassments.
Log a schema change, a duplicate load, a gauge with missing days, etc. as you hit
them. Do not silently patch an incident without an entry here.

## Incident: BOM's Somerset storage % is stale relative to Seqwater's own reduced-FSL reference

BOM's and Seqwater's Somerset **volume** series agree to within ~0.01-0.2% for
the same date. Their **percentage** series don't: BOM reports ~96.9% where
Seqwater reports ~79.0% for the same day. Root cause: BOM's % is computed
against a reference capacity that was never updated to reflect Seqwater's own
reduced full supply level (the SEQ grid's Somerset/Wivenhoe FSLs were reduced
via a 2020-11-06 licence amendment - see `seeds/dam_grid_membership.csv` /
`dim_dam`'s `reduced_fsl_note`). Handled by: keeping BOM's Somerset sources as
`optional: True` cross-checks in `ingest/config.py`, never modeled as the
grid's truth; `dbt/models/intermediate/int_somerset_cross_check.sql` keeps
the discrepancy queryable rather than silently picking one source. Full
recon trail in `docs/decisions.md`.

## Incident: earlier conclusion "Seqwater's page has no data" was wrong

An initial check of `https://www.seqwater.com.au/dam-levels` searched the raw
HTML for dam names/percentages and inspected only the first match (which
landed in intro prose), concluding the page was JS-rendered with no embedded
data. That was wrong - a real `<table class="dam-levels-table">` further down
the page has current data for all 12 grid dams, and
`/historic-dam-levels` inlines a full daily historical JSON blob. The wrong
conclusion stood until directly challenged ("are there other sources for
this data?"). See `docs/decisions.md` for the full correction and what was
built once the real data was found.

## Known gaps (do not invent data to fill these - SPEC.md section 3.3)

- **Seqwater's historic-dam-levels page defaults to ~5 years of daily
  history**, not the full period back to 2008-07-01 the page's own date
  picker allows - widening it requires replaying a Drupal AJAX form
  submission, attempted but not yet successful (see docs/decisions.md TODO
  list). 5 years of real daily data for all 12 dams is landed today regardless.
- Retailer demand time series: not published; demand is derived as
  population x per-capita litres/day, surfaced on the dashboard as a stated
  assumption, not a fact.
- Desal / recycled water production: annual totals only, no daily series.
- Per-dam inflow/release: patchy; preferring derived net storage change over
  claimed measured inflow.

## TODO-VERIFY markers outstanding

- `seeds/dam_grid_membership.csv`: `bom_site_id` and `catchment` are
  `TODO-VERIFY` for 11 of 12 dams (only Somerset's `bom_site_id` is confirmed
  real - everything else about the 12 dams, including FSL/capacity, now comes
  from the real automated `seqwater_dam_fsl_snapshot` ingest source instead
  of a seed).
- `ingest/config.py`'s `silo_brisbane_rainfall` entry: `station_no` is
  `TODO-VERIFY` and blocked on a real `SILO_API_KEY` (see below).

## Source caveats

- **SILO**: gap-filled data, explicitly not suitable for climate-change-detection
  claims per the source's own documentation - use it for catchment rainfall history
  only. See the caveat repeated in `ingest/silo.py`.
