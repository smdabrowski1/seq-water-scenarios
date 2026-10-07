# Seeds

Versioned CSVs for hand-keyed or one-off-downloaded reference data (dam metadata,
drought trigger thresholds, supply options, population/climate projections,
per-capita demand assumptions). See SPEC.md section 3.2 for the full list and where
each one comes from.

**Every seed file carries `source_url` and `as_at_date` columns on every row. No
exceptions.** This is a dbt custom test (SPEC.md section 5) - a seed row with a null
in either column should fail `dbt test`, not slip through.

If a real figure isn't available yet, put `TODO-VERIFY` in the relevant column
rather than fabricating a number - see SPEC.md section 9's "never fabricate a
figure" rule.

**Prefer an automated ingest source over a seed whenever the data is actually
fetchable.** `dam_grid_membership.csv` is deliberately small: it holds only
the facts that genuinely cannot be scraped (BOM's own site-id crosswalk,
catchment area) plus the 12-dam grid-membership flag itself (a categorization
from SPEC.md, not something any API returns). Everything that *can* be
fetched - dam names, current/historical volume and %, full supply volume,
reduced-FSL notices - comes from `ingest/seqwater_scrape.py`'s
`seqwater_dam_fsl_snapshot` and `seqwater_dam_levels_historical` sources
instead, landed as parquet like any other ingest source, not hand-transcribed
into a CSV. A seed is for what a human has to know, not what a scraper
already told you.
