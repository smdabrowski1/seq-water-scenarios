{{ config(tags=["scenario_output"]) }}

-- Silver: light typing only, one row per (scenario, supply option).
-- Deduplicated to the most recent `dt` partition per (scenario_name,
-- option_name). `lead_time_years` stays text here (carries real
-- `TODO-VERIFY` values through, same convention as seed_supply_options
-- itself) - cast happens only where a model actually needs it numerically.
with ranked as (
    select
        *,
        row_number() over (
            partition by scenario_name, option_name order by dt desc
        ) as rn
    from {{ source('scenarios_raw', 'scenario_commit_by') }}
)

select
    scenario_name,
    option_name,
    balance_negative_year,
    lead_time_years,
    commit_by_year,
    yield_gl_per_year
from ranked
where rn = 1
