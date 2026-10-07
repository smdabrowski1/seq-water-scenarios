{{ config(tags=["scenario_output"]) }}

-- Silver: light typing only, one row per (scenario, year). Deduplicated to
-- the most recent `dt` partition per (scenario_name, year).
with ranked as (
    select
        *,
        row_number() over (
            partition by scenario_name, year order by dt desc
        ) as rn
    from {{ source('scenarios_raw', 'scenario_balance') }}
)

select
    scenario_name,
    year,
    population_total,
    demand_ml_per_year,
    safe_yield_ml_per_year,
    available_yield_ml_per_year,
    surplus_deficit_ml_per_year
from ranked
where rn = 1
