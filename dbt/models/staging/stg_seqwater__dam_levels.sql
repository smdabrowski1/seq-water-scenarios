-- Silver: light typing/renaming over the full 25-dam + grid-total feed
-- (staging mirrors the source faithfully - scoping to the 12-dam grid happens
-- downstream in intermediate/marts, not here).
--
-- Deduplicated to the most recent `dt` partition per (storage_date, dam_name):
-- this source is a full ~5-year refetch every run, not an incremental append,
-- so once more than one dt= partition exists on disk (raw partitions are
-- immutable, never deleted), the same row would otherwise appear once per
-- partition - a real bug that silently doubled fct_grid_storage_daily until
-- fixed (see docs/decisions.md).
with ranked as (
    select
        storage_date,
        {{ normalize_dam_name('dam_name') }} as dam_name,
        level_pct,
        volume_ml,
        source_id,
        (level_pct is null and volume_ml is null) as is_gap,
        row_number() over (
            partition by storage_date, {{ normalize_dam_name('dam_name') }}
            order by dt desc
        ) as rn
    from {{ source('raw', 'seqwater_dam_levels_historical') }}
)

select storage_date, dam_name, level_pct, volume_ml, source_id, is_gap
from ranked
where rn = 1
