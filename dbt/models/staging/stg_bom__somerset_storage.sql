-- Silver: Somerset's BOM storage volume (ML), light typing only. Scenario-
-- engine calibration input, not a dashboard source - see _sources.yml.
--
-- `timestamp` comes in with a real UTC-correct instant but an arbitrary
-- session display timezone (confirmed live - DuckDB showed "Asia/Makassar"
-- even though the source data is Queensland/AEST) - converting explicitly to
-- `Australia/Brisbane` before taking the date recovers the intended local
-- calendar date regardless of session tz, rather than trusting whatever the
-- display timezone happens to be.
--
-- Deduplicated to the most recent `dt` partition per storage_date, same
-- reason as every other source here - this is a full-history refetch each
-- run (constant while `to_date` stays pinned - see ingest/config.py), not an
-- incremental append.
with typed as (
    select
        cast(timestamp at time zone 'Australia/Brisbane' as date) as storage_date,
        value as storage_volume_ml,
        quality_code,
        dt
    from {{ source('raw', 'bom_somerset_storage_volume') }}
    where value is not null  -- quality_code=-1 rows are pending/unpublished, not real zeros
),

ranked as (
    select
        *,
        row_number() over (
            partition by storage_date
            order by dt desc
        ) as rn
    from typed
)

select storage_date, storage_volume_ml, quality_code
from ranked
where rn = 1
