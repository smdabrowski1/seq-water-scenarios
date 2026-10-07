-- Gold: per-dam daily storage, for the dashboard's "per-dam breakdown" view
-- (SPEC.md section 7, view 1). All 12 SEQ Water Grid dams, real data.
select
    i.storage_date,
    i.dam_name,
    i.storage_volume_ml,
    i.storage_level_pct,
    i.is_gap
from {{ ref('int_storage_daily') }} as i
order by i.storage_date, i.dam_name
