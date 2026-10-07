-- Silver: dam x day, volume ML + level %, gap-flagged. Per SPEC.md section 5's
-- int_storage_daily spec - now real for all 12 SEQ Water Grid dams (Seqwater
-- is the primary source; see docs/decisions.md for why BOM only covers one
-- of the 12 and isn't used here).
select
    l.storage_date,
    l.dam_name,
    l.volume_ml as storage_volume_ml,
    l.level_pct as storage_level_pct,
    l.is_gap
from {{ ref('stg_seqwater__dam_levels') }} as l
inner join {{ ref('stg_seed__dam_grid_membership') }} as d
    on l.dam_name = d.dam_name
where d.grid_member
