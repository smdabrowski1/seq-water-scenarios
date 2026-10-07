{{ config(tags=["scenario_output"]) }}

-- Silver: light typing only, one row per named scenario. Deduplicated to the
-- most recent `dt` partition per scenario_name - same reason as every other
-- source here (a full re-run of every scenario each time, not an incremental
-- append).
with ranked as (
    select
        *,
        row_number() over (partition by scenario_name order by dt desc) as rn
    from {{ source('scenarios_raw', 'scenario_dim') }}
)

select
    scenario_name,
    description,
    population_series,
    per_capita_demand_tier,
    per_capita_l_per_day,
    climate_time_slice,
    climate_scenario,
    rainfall_replay_type,
    rainfall_replay_start_year,
    rainfall_replay_n_quarters,
    n_analogues_in_fan,
    safe_yield_ml_per_year,
    available_yield_ml_per_year,
    balance_negative_year
from ranked
where rn = 1
