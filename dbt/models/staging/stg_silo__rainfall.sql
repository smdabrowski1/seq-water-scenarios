-- Silver: light typing/renaming only. One row per (date, dam_name) - a
-- single grid-cell reading per dam, not an area-weighted catchment average
-- (see the source's own description in _sources.yml for why).
--
-- Deduplicated to the most recent `dt` partition per (rainfall_date,
-- dam_name) - same reason as the other Seqwater sources: this is a full
-- ~40-year refetch every run, not an incremental append.
with ranked as (
    select
        rainfall_date,
        dam_name,
        lat,
        lon,
        rainfall_mm,
        source_code,
        row_number() over (
            partition by rainfall_date, dam_name
            order by dt desc
        ) as rn
    from {{ source('raw', 'silo_catchment_rainfall') }}
)

select rainfall_date, dam_name, lat, lon, rainfall_mm, source_code
from ranked
where rn = 1
