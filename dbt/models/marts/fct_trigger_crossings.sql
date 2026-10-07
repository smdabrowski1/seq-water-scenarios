{{ config(tags=["scenario_output"]) }}

-- Gold: scenario x trigger - probability and expected timing of crossing
-- each real Seqwater drought-response threshold (SPEC.md section 5).
-- Triggers are the actual ones from Seqwater's 2023 Water Security Program
-- (Figure 10 - pre-drought 70%, drought-declared 50%, extreme-drought 25%,
-- EMSV 8-10%), not invented thresholds - see docs/decisions.md.
--
-- `expected_crossing_date` maps the median crossing quarter-offset (among
-- analogues that cross at all) onto a real future calendar date, same
-- current_date-anchored approach as fct_scenario_trajectory - null when no
-- analogue in the fan ever crosses that trigger.
select
    scenario_name,
    trigger_name,
    trigger_pct,
    trigger_threshold_ml,
    n_analogues_crossing,
    n_analogues_total,
    crossing_probability,
    case
        when median_crossing_quarter_offset is not null
            then current_date + to_months(cast(median_crossing_quarter_offset * 3 as integer))
    end as expected_crossing_date
from {{ ref('stg_scenarios__trigger_crossings') }}
order by scenario_name, trigger_pct desc
