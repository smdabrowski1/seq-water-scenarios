-- Real grain of fct_grid_storage_daily is (storage_date, series), not just
-- storage_date - only true today because `series` is always 'observed', but
-- expressed this way now so it stays correct once fct_scenario_trajectory
-- (Phase 3) adds more series values without anyone needing to remember to
-- come back and fix this test. No dbt_utils dependency needed for a plain
-- group-by-having check.
select storage_date, series, count(*) as row_count
from {{ ref('fct_grid_storage_daily') }}
group by storage_date, series
having count(*) > 1
