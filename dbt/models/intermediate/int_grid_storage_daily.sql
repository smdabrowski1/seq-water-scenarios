-- Silver: grid total ML and %, the headline series (SPEC.md section 5). This
-- is Seqwater's own precomputed "SEQ Water Grid" aggregate (the source's g/l
-- fields), not re-derived by summing int_storage_daily - Seqwater's aggregate
-- is scoped to the 12 grid dams by definition, so there's nothing to
-- recompute, and re-summing risks silently drifting from their own number.
select
    storage_date,
    volume_ml as grid_storage_volume_ml,
    level_pct as grid_storage_pct,
    is_gap
from {{ ref('stg_seqwater__dam_levels') }}
where dam_name = 'SEQ Water Grid'
