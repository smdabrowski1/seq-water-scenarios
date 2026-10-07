{{ config(tags=["scenario_output"]) }}

-- Gold: scenario x projected date, storage trajectory with percentile bands
-- across the analogue fan (SPEC.md section 5 / 6.1). Grain is
-- (scenario_name, quarter_offset) - percentile bands computed across every
-- historical analogue's simulated storage at that same offset, not across
-- calendar dates (each analogue starts at a different real historical year,
-- so "offset from today" is what's actually comparable across them).
-- `projected_date` maps that offset onto a real future calendar quarter from
-- today, for direct plotting - a single-analogue scenario (e.g. the
-- Millennium Drought Repeat scenarios) has p10 = p50 = p90 (one real
-- trajectory, not a statistical spread), which is correct, not a bug.
--
-- `any_beyond_validated_range` is true if ANY analogue contributing to this
-- quarter's band exceeds the water-balance model's observed calibration
-- range - a real, honest caveat that must stay visible on the dashboard, not
-- buried (see docs/decisions.md, 2026-10-05: 62% of the generic fan
-- triggers this at some point).
select
    scenario_name,
    quarter_offset,
    current_date + to_months(cast(quarter_offset * 3 as integer)) as projected_date,
    percentile_cont(0.1) within group (order by storage_ml) as storage_p10_ml,
    percentile_cont(0.5) within group (order by storage_ml) as storage_p50_ml,
    percentile_cont(0.9) within group (order by storage_ml) as storage_p90_ml,
    count(*) as n_analogues,
    bool_or(beyond_validated_range) as any_beyond_validated_range
from {{ ref('stg_scenarios__trajectory') }}
group by scenario_name, quarter_offset
order by scenario_name, quarter_offset
