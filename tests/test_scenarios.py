from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from scenarios.analogues import (
    build_analogue_fan,
    quarterly_regional_rainfall,
    replay_analogue,
    simulate_trajectory,
)
from scenarios.climate import apply_climate_adjustment
from scenarios.demand import project_demand_ml_per_year
from scenarios.engine import (
    compute_commit_by_dates,
    find_balance_negative_year,
    find_safe_yield,
)


def test_simulate_trajectory_constant_rainfall():
    # alpha=-100, beta=2: at rainfall=50, change = -100 + 2*50 = 0 each step.
    trajectory = simulate_trajectory(
        [50, 50, 50], start_storage_ml=1000, alpha_ml_per_quarter=-100, beta_ml_per_mm=2
    )
    assert trajectory == [1000, 1000, 1000, 1000]


def test_simulate_trajectory_declining():
    trajectory = simulate_trajectory(
        [0, 0], start_storage_ml=1000, alpha_ml_per_quarter=-100, beta_ml_per_mm=2
    )
    assert trajectory == [1000, 900, 800]


def test_quarterly_regional_rainfall_averages_across_dams():
    daily = pl.DataFrame(
        {
            "rainfall_date": [date(2020, 1, 1), date(2020, 1, 1), date(2020, 1, 2)],
            "dam_name": ["A", "B", "A"],
            "rainfall_mm": [10.0, 20.0, 5.0],
        }
    )
    result = quarterly_regional_rainfall(daily)
    assert result.height == 1
    # day1 regional avg = 15 (A=10,B=20), day2 regional avg = 5 (A only) -> sum = 20
    assert result["regional_rainfall_mm"][0] == pytest.approx(20.0)


def test_replay_analogue_raises_when_not_enough_quarters():
    qr = pl.DataFrame(
        {
            "quarter_start": [date(2020, 1, 1), date(2020, 4, 1)],
            "regional_rainfall_mm": [100.0, 100.0],
        }
    )
    with pytest.raises(ValueError, match="doesn't have"):
        replay_analogue(2020, 4, qr, 1000.0, -10, 1, 0, 1000)


def test_replay_analogue_flags_beyond_validated_range():
    qr = pl.DataFrame(
        {
            "quarter_start": [date(2020, 1, 1), date(2020, 4, 1)],
            "regional_rainfall_mm": [50.0, 5000.0],  # second value way outside any real range
        }
    )
    result = replay_analogue(2020, 2, qr, 1000.0, -10, 1, 0, 1000)
    assert result["beyond_validated_range"] is True
    assert result["trajectory_ml"][0] == 1000.0


def test_build_analogue_fan_skips_short_windows():
    qr = pl.DataFrame(
        {
            "quarter_start": [date(y, 1, 1) for y in (2020, 2021)],
            "regional_rainfall_mm": [100.0, 100.0],
        }
    )
    fan = build_analogue_fan(qr, 1000.0, -10, 1, 0, 1000, n_quarters=4)
    assert fan == []  # neither start-year has 4 full quarters on record


def test_project_demand_ml_per_year_interpolates_and_sums_across_lgas():
    pop = pl.DataFrame(
        {
            "lga": ["A", "A", "B", "B"],
            "year": [2020, 2022, 2020, 2022],
            "population": [1000.0, 1200.0, 2000.0, 2000.0],
        }
    )
    result = project_demand_ml_per_year(pop, per_capita_l_per_day=100.0)
    assert result["year"].to_list() == [2020, 2021, 2022]
    # 2021 interpolated: A=1100, B=2000 -> total=3100
    row_2021 = result.filter(pl.col("year") == 2021)
    assert row_2021["population_total"][0] == pytest.approx(3100.0)
    expected_demand = 3100.0 * 100.0 * 365 / 1e6
    assert row_2021["demand_ml_per_year"][0] == pytest.approx(expected_demand)


def test_apply_climate_adjustment_none_is_passthrough():
    rainfall = pl.Series([100.0, 200.0])
    result = apply_climate_adjustment(rainfall, pl.DataFrame(), None, "none")
    assert result.to_list() == [100.0, 200.0]


def test_apply_climate_adjustment_scales_by_real_pct():
    rainfall = pl.Series([100.0, 200.0])
    projections = pl.DataFrame(
        {"time_slice": [2050], "scenario": ["SSP3-7.0"], "rainfall_pct_change": [-10.0]}
    )
    result = apply_climate_adjustment(rainfall, projections, 2050, "SSP3-7.0")
    assert result.to_list() == pytest.approx([90.0, 180.0])


def test_apply_climate_adjustment_raises_on_no_match():
    rainfall = pl.Series([100.0])
    projections = pl.DataFrame(
        {"time_slice": [2050], "scenario": ["SSP3-7.0"], "rainfall_pct_change": [-10.0]}
    )
    with pytest.raises(ValueError, match="expected exactly one"):
        apply_climate_adjustment(rainfall, projections, 2090, "SSP1-2.6")


def test_find_safe_yield_zero_when_even_lowest_demand_fails():
    # A fan where the trajectory starts already below any realistic threshold.
    fan = [{"rainfall_mm": [0, 0], "trajectory_ml": [100, 100, 100]}]
    safe_yield = find_safe_yield(
        fan,
        alpha_ml_per_quarter=0,
        beta_ml_per_mm=0,
        baseline_demand_ml_per_quarter=0,
        critical_threshold_ml=1000,
        search_low_ml_per_year=10,
        search_high_ml_per_year=100,
    )
    assert safe_yield == 0.0


def test_find_balance_negative_year_returns_first_exceeding_year():
    demand = pl.DataFrame({"year": [2020, 2021, 2022], "demand_ml_per_year": [50.0, 150.0, 200.0]})
    assert find_balance_negative_year(demand, available_yield_ml_per_year=100.0) == 2021


def test_find_balance_negative_year_none_when_never_exceeds():
    demand = pl.DataFrame({"year": [2020, 2021], "demand_ml_per_year": [50.0, 60.0]})
    assert find_balance_negative_year(demand, available_yield_ml_per_year=100.0) is None


def test_compute_commit_by_dates_subtracts_lead_time_and_skips_todo_verify():
    supply = pl.DataFrame(
        {
            "option_name": ["real_option", "unknown_option"],
            "lead_time_years": ["5", "TODO-VERIFY"],
        }
    )
    result = compute_commit_by_dates(2040, supply)
    assert result["real_option"] == 2035
    assert result["unknown_option"] is None


def test_compute_commit_by_dates_all_none_when_no_balance_negative_year():
    supply = pl.DataFrame({"option_name": ["a", "b"], "lead_time_years": ["5", "10"]})
    result = compute_commit_by_dates(None, supply)
    assert result == {"a": None, "b": None}
