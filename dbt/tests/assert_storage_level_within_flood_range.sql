-- Custom business test (SPEC.md section 2): a storage level reading is a
-- flood-operations state above 100%, not a data error, but anything beyond a
-- generous flood-compartment ceiling is worth a warning, not a silent pass.
-- No package dependency (dbt_utils) needed for a single-column range check.
-- Covers both per-dam and grid-total grain.
{{ config(severity='warn') }}

select storage_date, dam_name, storage_level_pct as level_pct
from {{ ref('fct_dam_storage_daily') }}
where storage_level_pct is not null
  and (storage_level_pct < 0 or storage_level_pct > 150)

union all

select storage_date, 'SEQ Water Grid' as dam_name, grid_storage_pct as level_pct
from {{ ref('fct_grid_storage_daily') }}
where grid_storage_pct is not null
  and (grid_storage_pct < 0 or grid_storage_pct > 150)
