{{ config(tags=["scenario_output"]) }}

-- Gold: scenario dimension (SPEC.md section 5). One row per named scenario
-- (scenarios/config/scenarios.yml), its configuration and top-line results.
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
from {{ ref('stg_scenarios__dim') }}
