{{ config(tags=["scenario_output"]) }}

-- Gold: scenario x year - available yield, projected demand, surplus/
-- deficit (SPEC.md section 5). The WRMP-style chart data: "declining yield
-- vs demand growth envelope" (SPEC.md section 7, view 4 - "the money shot").
--
-- Commit-by dates per supply option are a separate mart (fct_commit_by_dates)
-- rather than columns here, a deliberate deviation from the spec's literal
-- wording ("the trigger date for each supply option" as a column on this
-- table) - a commit-by date has grain (scenario, option), not (scenario,
-- year); forcing it into this table's grain would mean repeating the same
-- option's commit-by date on every year's row, which is confusing, not
-- clarifying. Noted in docs/decisions.md.
select
    scenario_name,
    year,
    population_total,
    demand_ml_per_year,
    safe_yield_ml_per_year,
    available_yield_ml_per_year,
    surplus_deficit_ml_per_year
from {{ ref('stg_scenarios__balance') }}
order by scenario_name, year
