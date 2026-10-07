"""Historical rainfall analogues: replay each observed historical year's
regional rainfall sequence forward from today's actual starting Grid storage,
producing a fan of trajectories. See SPEC.md section 6.1.

Operates on the Grid total, not per-dam - see docs/decisions.md's 2026-10-05
entry for why (the per-dam, Somerset-calibrated design was tried first and
failed real out-of-sample validation; the Grid-total model against regional
rainfall is what actually validates, leave-one-out CV R^2 = 0.627).
"""

from __future__ import annotations

import polars as pl


def quarterly_regional_rainfall(daily_rainfall: pl.DataFrame) -> pl.DataFrame:
    """`daily_rainfall`: one row per (dam, day) with `rainfall_date`,
    `rainfall_mm` (e.g. `fct_dam_rainfall_daily`). Averages across the 12
    catchments per day, then sums into quarters - must match exactly how
    `int_grid_water_balance_coefficients` was fit (same averaging, same
    `date_trunc('quarter', ...)` grain), or the fitted (alpha, beta) don't
    mean what this applies them to.
    """
    daily_regional = (
        daily_rainfall.group_by("rainfall_date")
        .agg(pl.col("rainfall_mm").mean().alias("regional_rainfall_mm"))
        .sort("rainfall_date")
    )
    return (
        daily_regional.with_columns(
            pl.col("rainfall_date").dt.truncate("1q").alias("quarter_start")
        )
        .group_by("quarter_start")
        .agg(pl.col("regional_rainfall_mm").sum().alias("regional_rainfall_mm"))
        .sort("quarter_start")
    )


def simulate_trajectory(
    quarterly_rainfall_mm: list[float],
    start_storage_ml: float,
    alpha_ml_per_quarter: float,
    beta_ml_per_mm: float,
) -> list[float]:
    """One quarter-step water-balance simulation. Returns
    `[start_storage_ml, storage after Q1, storage after Q2, ...]` - length
    `len(quarterly_rainfall_mm) + 1`.
    """
    trajectory = [start_storage_ml]
    storage = start_storage_ml
    for rain in quarterly_rainfall_mm:
        storage = storage + alpha_ml_per_quarter + beta_ml_per_mm * rain
        trajectory.append(storage)
    return trajectory


def replay_analogue(
    start_year: int,
    n_quarters: int,
    quarterly_regional: pl.DataFrame,
    start_storage_ml: float,
    alpha_ml_per_quarter: float,
    beta_ml_per_mm: float,
    observed_min_mm: float,
    observed_max_mm: float,
) -> dict:
    """Replays `n_quarters` of REAL historical regional rainfall starting at
    `start_year`'s first quarter, forward from `start_storage_ml` (today's
    real level, not the historical level - SPEC.md 6.1's "replay forward from
    today's actual starting storage"). Flags whether any quarter's rainfall
    fell outside the model's validated range - the Grid's real calibration
    history has no drought in it, so a drought-era replay (e.g. 1997) is
    likely genuine extrapolation, and that must be visible in the output, not
    silently absorbed into a confident-looking number (see docs/decisions.md).
    """
    start = pl.datetime(start_year, 1, 1)
    end_year = start_year + (n_quarters // 4) + 1
    window = (
        quarterly_regional.filter(
            (pl.col("quarter_start") >= start)
            & (pl.col("quarter_start") < pl.datetime(end_year, 1, 1))
        )
        .sort("quarter_start")
        .head(n_quarters)
    )
    if window.height < n_quarters:
        raise ValueError(
            f"start_year={start_year} doesn't have {n_quarters} full quarters "
            f"of real rainfall on record (only {window.height} available)"
        )
    rainfall_values = window["regional_rainfall_mm"].to_list()
    trajectory = simulate_trajectory(
        rainfall_values, start_storage_ml, alpha_ml_per_quarter, beta_ml_per_mm
    )
    beyond_validated_range = any(
        r < observed_min_mm or r > observed_max_mm for r in rainfall_values
    )
    return {
        "start_year": start_year,
        "quarter_starts": window["quarter_start"].to_list(),
        "rainfall_mm": rainfall_values,
        "trajectory_ml": trajectory,
        "beyond_validated_range": beyond_validated_range,
    }


def build_analogue_fan(
    quarterly_regional: pl.DataFrame,
    start_storage_ml: float,
    alpha_ml_per_quarter: float,
    beta_ml_per_mm: float,
    observed_min_mm: float,
    observed_max_mm: float,
    n_quarters: int = 12,
) -> list[dict]:
    """One replay per historical start-year that has a full `n_quarters`
    window on record - this is the "fan" (SPEC.md 6.1), a real trajectory per
    start-year, not a statistical distribution. Years without enough trailing
    record (the most recent ones) are skipped, not padded/guessed.
    """
    all_years = sorted(quarterly_regional["quarter_start"].dt.year().unique().to_list())
    results = []
    for year in all_years:
        try:
            results.append(
                replay_analogue(
                    year,
                    n_quarters,
                    quarterly_regional,
                    start_storage_ml,
                    alpha_ml_per_quarter,
                    beta_ml_per_mm,
                    observed_min_mm,
                    observed_max_mm,
                )
            )
        except ValueError:
            continue
    return results
