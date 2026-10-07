{{ config(tags=["scenario_output"]) }}

-- Silver: light typing only, one row per (scenario, analogue start-year,
-- quarter offset). Deduplicated to the most recent `dt` partition per
-- (scenario_name, analogue_start_year, quarter_offset).
with ranked as (
    select
        *,
        row_number() over (
            partition by scenario_name, analogue_start_year, quarter_offset
            order by dt desc
        ) as rn
    from {{ source('scenarios_raw', 'scenario_trajectory') }}
)

select
    scenario_name,
    analogue_start_year,
    quarter_offset,
    source_rainfall_date,
    rainfall_mm,
    storage_ml,
    beyond_validated_range
from ranked
where rn = 1
