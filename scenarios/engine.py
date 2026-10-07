"""Scenario engine: combines rainfall analogues, climate adjustment, and demand
projections into named scenarios, producing storage trajectories and commit-by
dates for supply options. See SPEC.md section 6 for the method; see
docs/decisions.md's 2026-10-05 entry for why the water-balance model is
Grid-total (not per-dam) and what its real, validated limits are.

**Demand adjustment, a real simplifying assumption, named here rather than
hidden**: the fitted `alpha` (int_grid_water_balance_coefficients) is a
residual that already embeds whatever mix of demand draw, evaporation, and
operational release actually occurred during the 2021-2026 calibration
window - there's no way to cleanly separate "how much of alpha was literally
household demand" from the rest with the data available. To project a
*different* future demand scenario, this engine adjusts alpha by the delta
between the scenario's demand and a fixed real baseline (medium population
series x status-quo 160 L/day, averaged over the calibration window) and
assumes the non-demand component (evaporation + typical release pattern)
stays constant regardless of which demand scenario is being run. This is
named explicitly in the mandatory limitations section, not left implicit.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from scenarios.analogues import simulate_trajectory
from scenarios.demand import project_demand_ml_per_year

# EMSV (Essential Minimum Supply Volume) trigger: 8-10% of Grid storage,
# Seqwater's own most severe drought-response tier (SPEC.md research this
# session, Water Security Program 2023 p.34). Using the upper/safer bound
# (10%) as the critical threshold a safe yield must never cross.
EMSV_TRIGGER_PCT = 10.0

# Real baseline used only to compute the demand *delta* applied to alpha -
# see module docstring. Not a scenario choice itself.
BASELINE_POPULATION_SERIES = "medium"
BASELINE_PER_CAPITA_L_PER_DAY = 160.0  # "status_quo" tier, seed_per_capita_demand
BASELINE_CALIBRATION_YEARS = (2021, 2026)  # matches int_grid_water_balance_coefficients' fit window


@dataclass
class ScenarioResult:
    scenario_name: str
    fan: list[dict]  # one trajectory dict per historical start-year, from build_analogue_fan
    demand_curve: pl.DataFrame  # year, population_total, demand_ml_per_year
    safe_yield_ml_per_year: float
    available_yield_ml_per_year: float  # safe_yield + existing climate-independent sources
    balance_negative_year: int | None
    commit_by_dates: dict[str, int | None]  # option_name -> year, or None if lead time unknown


def baseline_demand_ml_per_quarter(population_projections: pl.DataFrame) -> float:
    baseline = population_projections.filter(pl.col("series") == BASELINE_POPULATION_SERIES)
    curve = project_demand_ml_per_year(baseline, BASELINE_PER_CAPITA_L_PER_DAY)
    start, end = BASELINE_CALIBRATION_YEARS
    window = curve.filter((pl.col("year") >= start) & (pl.col("year") <= end))
    return window["demand_ml_per_year"].mean() / 4


def _simulate_fan_with_demand(
    fan: list[dict],
    alpha_ml_per_quarter: float,
    beta_ml_per_mm: float,
    baseline_demand_ml_per_quarter: float,
    scenario_demand_ml_per_year: float,
) -> list[list[float]]:
    """Re-simulates every analogue in `fan` with alpha adjusted for a
    different (constant, for this check) annual demand - see module
    docstring for why this is a delta adjustment, not an added raw term.
    """
    demand_delta_per_quarter = scenario_demand_ml_per_year / 4 - baseline_demand_ml_per_quarter
    adjusted_alpha = alpha_ml_per_quarter - demand_delta_per_quarter
    return [
        simulate_trajectory(
            analogue["rainfall_mm"],
            analogue["trajectory_ml"][0],
            adjusted_alpha,
            beta_ml_per_mm,
        )
        for analogue in fan
    ]


def find_safe_yield(
    fan: list[dict],
    alpha_ml_per_quarter: float,
    beta_ml_per_mm: float,
    baseline_demand_ml_per_quarter: float,
    critical_threshold_ml: float,
    search_low_ml_per_year: float = 50_000,
    search_high_ml_per_year: float = 600_000,
    tolerance_ml_per_year: float = 1_000,
) -> float:
    """Binary search for the maximum constant annual demand such that no
    analogue in `fan` ever drops below `critical_threshold_ml`. Same concept
    real water utilities call "system yield" (IQQM-style modelling, per this
    session's research) - "increase demand until the level of service
    objective is no longer valid."
    """

    def passes(demand_ml_per_year: float) -> bool:
        trajectories = _simulate_fan_with_demand(
            fan,
            alpha_ml_per_quarter,
            beta_ml_per_mm,
            baseline_demand_ml_per_quarter,
            demand_ml_per_year,
        )
        return all(min(t) >= critical_threshold_ml for t in trajectories)

    if not passes(search_low_ml_per_year):
        return 0.0  # even the lowest demand tested fails - real finding, not an error to hide

    low, high = search_low_ml_per_year, search_high_ml_per_year
    while high - low > tolerance_ml_per_year:
        mid = (low + high) / 2
        if passes(mid):
            low = mid
        else:
            high = mid
    return low


def find_balance_negative_year(
    demand_curve: pl.DataFrame, available_yield_ml_per_year: float
) -> int | None:
    """First year the demand curve exceeds available yield, or None if it
    never does within the demand curve's own horizon (2046, per
    seed_population_projections - a real limit, not infinite confidence
    the system is safe beyond that year)."""
    exceeding = demand_curve.filter(pl.col("demand_ml_per_year") > available_yield_ml_per_year)
    if exceeding.height == 0:
        return None
    return exceeding["year"].min()


def compute_commit_by_dates(
    balance_negative_year: int | None, supply_options: pl.DataFrame
) -> dict[str, int | None]:
    """balance_negative_year minus each option's lead_time_years - SPEC.md
    6.4's actual deliverable. Options with a TODO-VERIFY (non-numeric) lead
    time surface as None ("cannot compute"), never a guessed number."""
    if balance_negative_year is None:
        return {name: None for name in supply_options["option_name"].to_list()}

    results: dict[str, int | None] = {}
    for row in supply_options.iter_rows(named=True):
        lead_time = row["lead_time_years"]
        try:
            lead_time_years = int(lead_time)
        except (TypeError, ValueError):
            results[row["option_name"]] = None  # TODO-VERIFY or missing - not guessed
            continue
        results[row["option_name"]] = balance_negative_year - lead_time_years
    return results
