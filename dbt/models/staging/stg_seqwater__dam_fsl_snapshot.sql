-- Silver: light typing/renaming only. `full_supply_volume_ml` is the *current
-- operating* FSL (already reduced where reduced_fsl_note is non-null) - see
-- docs/decisions.md for why this can't be split into nominal-vs-reduced here
-- without guessing (Seqwater's own page states reductions as an approximate
-- percentage, not an exact nominal figure).
--
-- Deduplicated to the most recent `dt` partition per dam_name - this is a
-- current-state snapshot, not a time series, so every partition on disk has
-- the same 25 dams; without this, more than one partition existing would
-- fan out every downstream join (see docs/decisions.md for the real bug this
-- caused in dim_dam).
with ranked as (
    select
        {{ normalize_dam_name('dam_name') }} as dam_name,
        source_id,
        full_supply_volume_ml as current_fsl_ml,
        current_volume_ml,
        current_pct_full,
        nullif(comment, '') as comment,
        reduced_fsl_note,
        (reduced_fsl_note is not null) as has_reduced_fsl,
        row_number() over (
            partition by {{ normalize_dam_name('dam_name') }}
            order by dt desc
        ) as rn
    from {{ source('raw', 'seqwater_dam_fsl_snapshot') }}
)

select dam_name, source_id, current_fsl_ml, current_volume_ml, current_pct_full,
       comment, reduced_fsl_note, has_reduced_fsl
from ranked
where rn = 1
