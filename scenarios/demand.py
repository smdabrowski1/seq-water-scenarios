"""Demand projection: population(LGA, year, series) x per_capita_L_per_day x 365 / 1e6,
summed across SEQ LGAs. See SPEC.md section 6.3.

`seed_population_projections` only has 5-year steps (2021/2026/.../2046 - see
docs/decisions.md, 2026-10-02 entry) - QGSO's own native resolution, not
something this project chose. Linearly interpolated to annual here since the
scenario engine needs a year-by-year demand curve to find the balance-negative
year, not just five checkpoints.
"""

from __future__ import annotations

import polars as pl


def project_demand_ml_per_year(
    population_by_lga: pl.DataFrame,
    per_capita_l_per_day: float,
) -> pl.DataFrame:
    """`population_by_lga` is `seed_population_projections` pre-filtered to one
    `series` (low/medium/high) - columns `lga`, `year`, `population`, one row
    per (lga, year) at the native 5-year steps. Returns one row per year
    (interpolated, 2021-2046 inclusive), columns `year`, `population_total`,
    `demand_ml_per_year`.
    """
    lgas = population_by_lga["lga"].unique().sort()
    year_min, year_max = (
        population_by_lga["year"].min(),
        population_by_lga["year"].max(),
    )
    all_years = pl.DataFrame({"year": range(year_min, year_max + 1)})

    interpolated = []
    for lga in lgas:
        lga_rows = (
            population_by_lga.filter(pl.col("lga") == lga).select("year", "population").sort("year")
        )
        full = (
            all_years.join(lga_rows, on="year", how="left")
            .sort("year")
            .with_columns(pl.col("population").interpolate())
        )
        interpolated.append(full.with_columns(pl.lit(lga).alias("lga")))

    annual_by_lga = pl.concat(interpolated)

    return (
        annual_by_lga.group_by("year")
        .agg(pl.col("population").sum().alias("population_total"))
        .with_columns(
            (pl.col("population_total") * per_capita_l_per_day * 365 / 1e6).alias(
                "demand_ml_per_year"
            )
        )
        .sort("year")
    )
