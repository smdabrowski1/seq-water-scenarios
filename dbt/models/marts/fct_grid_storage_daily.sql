-- Gold: the observed grid storage history, per SPEC.md section 5's
-- fct_grid_storage_daily - the headline series (grid-total grain, one row
-- per day), sourced from Seqwater's own precomputed grid aggregate via
-- int_grid_storage_daily. See fct_dam_storage_daily for the per-dam breakdown.
--
-- `series = 'observed'` is a degenerate dimension, not a real key (there's
-- only ever one grid) - added so this table unions cleanly with the future
-- fct_scenario_trajectory (Phase 3, SPEC.md section 5: scenario x date,
-- projected grid storage) once it exists, e.g. `series = 'scenario_dry_2010'`
-- for a projected path. Without this column, a dashboard comparing observed
-- vs. projected would have nothing to distinguish rows on except which table
-- they came from.
select
    storage_date,
    'observed' as series,
    grid_storage_volume_ml,
    grid_storage_pct,
    is_gap
from {{ ref('int_grid_storage_daily') }}
order by storage_date
