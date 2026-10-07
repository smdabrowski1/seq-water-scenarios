{{ config(tags=["scenario_output"]) }}

-- Silver: light typing only, one row per (scenario, drought trigger).
-- Deduplicated to the most recent `dt` partition per (scenario_name,
-- trigger_name).
with ranked as (
    select
        *,
        row_number() over (
            partition by scenario_name, trigger_name order by dt desc
        ) as rn
    from {{ source('scenarios_raw', 'scenario_trigger_crossings') }}
)

select
    scenario_name,
    trigger_name,
    trigger_pct,
    trigger_threshold_ml,
    n_analogues_crossing,
    n_analogues_total,
    crossing_probability,
    median_crossing_quarter_offset
from ranked
where rn = 1
