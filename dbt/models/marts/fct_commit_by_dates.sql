{{ config(tags=["scenario_output"]) }}

-- Gold: scenario x supply option - the actual SPEC.md section 6.4
-- deliverable ("the commit-by date... is the number a planner would act
-- on"). See fct_supply_demand_balance's own comment for why this is a
-- separate mart rather than columns on that (scenario, year)-grain table.
--
-- `commit_by_year` is null when either the scenario never crosses
-- balance-negative within the demand curve's horizon (a real "the system
-- copes" finding, not missing data), or the option's lead time is a real,
-- disclosed `TODO-VERIFY` rather than a guessed number (see
-- seed_supply_options and docs/decisions.md, 2026-10-05).
select
    scenario_name,
    option_name,
    balance_negative_year,
    lead_time_years,
    commit_by_year
from {{ ref('stg_scenarios__commit_by') }}
order by scenario_name, option_name
