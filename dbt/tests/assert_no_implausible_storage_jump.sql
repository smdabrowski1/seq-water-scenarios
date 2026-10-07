-- Custom business test (SPEC.md section 5): no dam has a day-over-day volume
-- change exceeding a physically plausible bound - flagged as a warning, not a
-- hard failure, since a real flood-release event can genuinely move this much
-- water in a day and shouldn't block a build.
{{ config(severity='warn') }}

with daily_change as (
    select
        dam_name,
        storage_date,
        storage_volume_ml,
        storage_volume_ml - lag(storage_volume_ml) over (
            partition by dam_name order by storage_date
        ) as day_over_day_change_ml
    from {{ ref('fct_dam_storage_daily') }}
    where not is_gap
)

select *
from daily_change
where abs(day_over_day_change_ml) > 20000  -- ML/day; TODO-VERIFY a defensible bound per dam
