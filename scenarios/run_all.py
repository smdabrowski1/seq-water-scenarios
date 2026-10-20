"""Runs every named scenario in scenarios/config/scenarios.yml against the
real warehouse data, landing results as raw parquet (same write-temp-then-
os.replace() pattern as ingest/run_all.py) for the dbt staging/marts layer to
pick up. See SPEC.md section 6 for the method; docs/decisions.md's
2026-10-05 entries for why the model is Grid-total (not per-dam), what its
real validated limits are, and the real, sourced figures behind the demand/
supply-option inputs.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import polars as pl
import yaml

from scenarios.analogues import build_analogue_fan, quarterly_regional_rainfall, replay_analogue
from scenarios.climate import apply_climate_adjustment
from scenarios.demand import project_demand_ml_per_year
from scenarios.engine import (
    EMSV_TRIGGER_PCT,
    compute_commit_by_dates,
    find_safe_yield,
)
from scenarios.engine import baseline_demand_ml_per_quarter as compute_baseline_demand

# Real Seqwater drought-response triggers (Water Security Program 2023,
# Figure 10 - sourced this session, see docs/decisions.md). Used for
# fct_trigger_crossings: what fraction of a scenario's analogue fan crosses
# each threshold, and when.
DROUGHT_TRIGGERS = {
    "pre_drought": 70.0,
    "drought_declared": 50.0,
    "extreme_drought": 25.0,
    "emsv": EMSV_TRIGGER_PCT,
}

SCENARIOS_CONFIG_PATH = Path(__file__).parent / "config" / "scenarios.yml"
# GL/yr -> ML/yr. Only desal + recycled water here - SPEC.md's own domain
# primer names exactly these two as "climate-independent sources"
# (desal is literally seawater; recycled water's input is wastewater
# volume, which tracks population more than rainfall). Groundwater used to
# be folded into this same flat constant - a drift this code introduced,
# never something SPEC.md itself claimed - until a user question prompted
# checking: Seqwater's own North Stradbroke Island Drought Response Plan
# (seqwater.com.au/document/2261) monitors real aquifer bore-level drought
# triggers for this exact allocation, and a 2024 Redlands2030 report on the
# same aquifer states its level "hasn't even recovered" since the last
# drought - groundwater is not actually climate-independent, just slower
# and more buffered than a surface dam. See GROUNDWATER_FLOOR below for how
# its yield now varies year to year instead of staying flat.
EXISTING_DESAL_RECYCLED_ML_PER_YEAR = (43 + 59) * 1000
GROUNDWATER_FULL_ML_PER_YEAR = 16 * 1000  # seed_supply_options' sourced ceiling

# No sourced GL/yr-vs-drought-severity curve exists for the Grid-allocated
# portion of this aquifer specifically (checked live - the Drought Response
# Plan above gives real bore-level triggers and response actions, not a
# yield-reduction figure). First attempt tied the decay to grid *storage*
# trigger tiers (reusing DROUGHT_TRIGGERS) - wrong basis, confirmed by a user
# question: aquifer recharge responds to *rainfall*, not to how full the
# surface dams happen to be, and a flat scenario-wide figure doesn't actually
# decay at all, it's just one smaller constant. This version instead tracks
# a trailing 4-quarter average of the actual rainfall being replayed, scaled
# against the long-run historical average, recomputed every quarter - a real
# year-by-year curve, not a single number. **The floor (20%) and the use of
# a trailing-4-quarter window are still a reasoned assumption, not a sourced
# figure** - flagged as such wherever shown.
GROUNDWATER_FLOOR = 0.2
GROUNDWATER_TRAILING_QUARTERS = 4


def _groundwater_multiplier(
    trailing_avg_rainfall_mm: float, long_run_avg_rainfall_mm: float
) -> float:
    """1.0 at/above the long-run average quarterly rainfall, floor at zero
    rainfall, linear in between - continuous, not stepped."""
    ratio = max(0.0, min(1.0, trailing_avg_rainfall_mm / long_run_avg_rainfall_mm))
    return GROUNDWATER_FLOOR + (1 - GROUNDWATER_FLOOR) * ratio


def _land_parquet(df: pl.DataFrame, data_dir: Path, name: str, dt: str) -> None:
    partition_dir = data_dir / "scenarios" / name / f"dt={dt}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    final_path = partition_dir / f"{name}.parquet"
    tmp_path = partition_dir / f".tmp-{name}.parquet"
    df.write_parquet(tmp_path)
    os.replace(tmp_path, final_path)


def _quarter_offset_to_year(today, offset: int) -> int:
    """Same `current_date + to_months(offset*3)` basis fct_scenario_trajectory.sql
    uses for `projected_date` - kept in sync so a quarter's calendar year
    here matches what the dashboard's trajectory chart would show for it."""
    total_months = today.month - 1 + offset * 3
    return today.year + total_months // 12


def run_all(warehouse_path: Path, data_dir: Path, log_cb=None) -> None:
    log = log_cb or print
    today = datetime.now(UTC).date()
    dt = today.strftime("%Y-%m-%d")

    con = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        rainfall_rows = con.execute(
            "select rainfall_date, dam_name, rainfall_mm from fct_dam_rainfall_daily"
        ).fetchall()
        rainfall = pl.DataFrame(
            rainfall_rows, schema=["rainfall_date", "dam_name", "rainfall_mm"], orient="row"
        )
        quarterly_regional = quarterly_regional_rainfall(rainfall)
        # Real historical average, from the un-adjusted series (this is "what
        # normal looks like", not scaled by any scenario's climate factor) -
        # the baseline groundwater's rainfall-driven decay is measured against.
        long_run_avg_quarterly_rainfall_mm = quarterly_regional["regional_rainfall_mm"].mean()

        grid_latest = con.execute(
            "select grid_storage_volume_ml from fct_grid_storage_daily "
            "order by storage_date desc limit 1"
        ).fetchone()[0]

        beta, alpha, obs_min, obs_max = con.execute(
            "select beta_ml_per_mm, alpha_ml_per_quarter, "
            "observed_min_quarterly_rainfall_mm, observed_max_quarterly_rainfall_mm "
            "from int_grid_water_balance_coefficients"
        ).fetchone()

        full_capacity_ml = con.execute("select sum(current_fsl_ml) from dim_dam").fetchone()[0]

        pop_rows = con.execute(
            "select lga, series, year, population from seed_population_projections"
        ).fetchall()
        population = pl.DataFrame(
            pop_rows, schema=["lga", "series", "year", "population"], orient="row"
        )
        baseline_demand_ml_per_quarter = compute_baseline_demand(population)

        climate_rows = con.execute(
            "select time_slice, scenario, rainfall_pct_change from seed_climate_projections"
        ).fetchall()
        climate_projections = pl.DataFrame(
            climate_rows, schema=["time_slice", "scenario", "rainfall_pct_change"], orient="row"
        )

        demand_rows = con.execute(
            "select scenario, litres_per_day from seed_per_capita_demand"
        ).fetchall()
        per_capita_by_tier = {name: litres for name, litres in demand_rows}

        supply_rows = con.execute(
            "select option_name, lead_time_years, yield_gl_per_year from seed_supply_options"
        ).fetchall()
        supply_options = pl.DataFrame(
            supply_rows,
            schema=["option_name", "lead_time_years", "yield_gl_per_year"],
            orient="row",
        )
    finally:
        con.close()

    scenarios_config = yaml.safe_load(SCENARIOS_CONFIG_PATH.read_text())["scenarios"]

    dim_rows, trajectory_rows, balance_rows, commit_by_rows, trigger_rows = [], [], [], [], []

    for cfg in scenarios_config:
        name = cfg["name"]
        log(f"scenario {name}: starting")

        climate_cfg = cfg["climate_adjustment"]
        adjusted_rainfall = apply_climate_adjustment(
            quarterly_regional["regional_rainfall_mm"],
            climate_projections,
            climate_cfg["time_slice"],
            climate_cfg["scenario"],
        )
        qr_adjusted = quarterly_regional.with_columns(
            adjusted_rainfall.alias("regional_rainfall_mm")
        )

        replay_cfg = cfg["rainfall_replay"]
        if replay_cfg["type"] == "fan":
            fan = build_analogue_fan(
                qr_adjusted,
                grid_latest,
                alpha,
                beta,
                obs_min,
                obs_max,
                n_quarters=replay_cfg["n_quarters"],
            )
        elif replay_cfg["type"] == "fixed":
            fan = [
                replay_analogue(
                    replay_cfg["start_year"],
                    replay_cfg["n_quarters"],
                    qr_adjusted,
                    grid_latest,
                    alpha,
                    beta,
                    obs_min,
                    obs_max,
                )
            ]
        else:
            raise ValueError(f"unknown rainfall_replay.type: {replay_cfg['type']!r}")

        per_capita_l_per_day = per_capita_by_tier[cfg["per_capita_demand"]]
        population_for_scenario = population.filter(pl.col("series") == cfg["population_series"])
        demand_curve = project_demand_ml_per_year(population_for_scenario, per_capita_l_per_day)

        critical_threshold_ml = full_capacity_ml * EMSV_TRIGGER_PCT / 100
        safe_yield = find_safe_yield(
            fan, alpha, beta, baseline_demand_ml_per_quarter, critical_threshold_ml
        )

        # Groundwater's yield for each quarter of the replay, from a
        # trailing 4-quarter average of the actual (climate-adjusted)
        # rainfall being replayed at that point, scaled against the
        # long-run historical average - averaged across every analogue in
        # the fan first (one well-defined curve per scenario, not one per
        # analogue). A real year-by-year curve, not a flat scenario-wide
        # constant: it falls as the replayed drought deepens and climbs
        # back as the replayed rainfall recovers.
        n_quarters = replay_cfg["n_quarters"]
        avg_rainfall_by_offset = [
            sum(a["rainfall_mm"][i] for a in fan) / len(fan) for i in range(n_quarters)
        ]
        groundwater_yield_by_year: dict[int, float] = {}
        for offset in range(1, n_quarters + 1):
            window = avg_rainfall_by_offset[max(0, offset - GROUNDWATER_TRAILING_QUARTERS) : offset]
            trailing_avg = sum(window) / len(window)
            multiplier = _groundwater_multiplier(trailing_avg, long_run_avg_quarterly_rainfall_mm)
            year = _quarter_offset_to_year(today, offset)
            ml = GROUNDWATER_FULL_ML_PER_YEAR * multiplier
            # A calendar year can span more than one quarter_offset -
            # average rather than overwrite, so every quarter in that year
            # contributes, not just whichever was computed last.
            prior = groundwater_yield_by_year.get(year)
            groundwater_yield_by_year[year] = ml if prior is None else (prior + ml) / 2

        # Demand-curve years beyond the replay window (it only covers 3-13
        # years; the demand curve runs to 2046) get groundwater's full,
        # undecayed value - there's no simulated rainfall out there to
        # justify assuming continued drought past what was actually replayed.
        balance_negative_year = None
        for row in demand_curve.iter_rows(named=True):
            groundwater_ml = groundwater_yield_by_year.get(
                row["year"], GROUNDWATER_FULL_ML_PER_YEAR
            )
            available_yield_this_year = (
                safe_yield + EXISTING_DESAL_RECYCLED_ML_PER_YEAR + groundwater_ml
            )
            surplus_deficit = available_yield_this_year - row["demand_ml_per_year"]
            if surplus_deficit < 0 and balance_negative_year is None:
                balance_negative_year = row["year"]
            balance_rows.append(
                {
                    "scenario_name": name,
                    "year": row["year"],
                    "population_total": row["population_total"],
                    "demand_ml_per_year": row["demand_ml_per_year"],
                    "safe_yield_ml_per_year": safe_yield,
                    "available_yield_ml_per_year": available_yield_this_year,
                    "groundwater_yield_ml_per_year": groundwater_ml,
                    "surplus_deficit_ml_per_year": surplus_deficit,
                }
            )
        commit_by = compute_commit_by_dates(balance_negative_year, supply_options)

        for analogue in fan:
            # quarter_offset is what the dashboard actually plots against (N
            # quarters from today, mapped to a real future calendar date
            # downstream in dbt) - offset 0 MUST be today's actual starting
            # storage (trajectory_ml[0], identical across every analogue),
            # not "after one quarter of that analogue's own rainfall".
            # Previously this loop started at trajectory_ml[1:], silently
            # dropping the real anchor point - every analogue then disagreed
            # at offset 0 (it's already one quarter of divergent rainfall
            # in), which the dashboard rendered as a visible jump right at
            # the observed/projected splice. Confirmed live: baseline's
            # offset-0 p50 was ~1.84M ML against a real latest observed
            # storage of ~1.75M ML - an ~88,000 ML discontinuity that had
            # nothing to do with the model, just a dropped data point.
            for offset, storage in enumerate(analogue["trajectory_ml"]):
                if offset == 0:
                    q_start, rain = None, None
                else:
                    q_start = analogue["quarter_starts"][offset - 1]
                    rain = analogue["rainfall_mm"][offset - 1]
                trajectory_rows.append(
                    {
                        "scenario_name": name,
                        "analogue_start_year": analogue["start_year"],
                        "quarter_offset": offset,
                        "source_rainfall_date": q_start,
                        "rainfall_mm": rain,
                        "storage_ml": storage,
                        "beyond_validated_range": analogue["beyond_validated_range"],
                    }
                )

        for option_name, commit_year in commit_by.items():
            option_row = supply_options.filter(pl.col("option_name") == option_name)
            lead_time = option_row["lead_time_years"][0]
            # Stays text, same convention as lead_time_years - a real,
            # disclosed TODO-VERIFY (Second desalination plant) is kept
            # visible through the pipeline, never cast/coerced away. Back to
            # the static seed ceiling here, including for groundwater - its
            # real, varying figure now lives per-year in `balance_rows`
            # (groundwater_yield_ml_per_year), which is where a per-year
            # number actually belongs; this table only ever had one row per
            # (scenario, option), which can't represent "decays every year"
            # - it was overridden with a single decayed figure for one
            # session but that was a worse fit than just reverting.
            yield_gl_per_year = option_row["yield_gl_per_year"][0]
            commit_by_rows.append(
                {
                    "scenario_name": name,
                    "option_name": option_name,
                    "balance_negative_year": balance_negative_year,
                    "lead_time_years": lead_time,
                    "commit_by_year": commit_year,
                    "yield_gl_per_year": yield_gl_per_year,
                }
            )

        n_analogues = len(fan)
        for trigger_name, trigger_pct in DROUGHT_TRIGGERS.items():
            threshold_ml = full_capacity_ml * trigger_pct / 100
            crossing_offsets = []
            for analogue in fan:
                trajectory = analogue["trajectory_ml"][1:]  # exclude the starting point
                for offset, storage in enumerate(trajectory):
                    if storage < threshold_ml:
                        crossing_offsets.append(offset)
                        break
            n_crossing = len(crossing_offsets)
            trigger_rows.append(
                {
                    "scenario_name": name,
                    "trigger_name": trigger_name,
                    "trigger_pct": trigger_pct,
                    "trigger_threshold_ml": threshold_ml,
                    "n_analogues_crossing": n_crossing,
                    "n_analogues_total": n_analogues,
                    "crossing_probability": n_crossing / n_analogues if n_analogues else None,
                    "median_crossing_quarter_offset": (
                        sorted(crossing_offsets)[len(crossing_offsets) // 2]
                        if crossing_offsets
                        else None
                    ),
                }
            )

        dim_rows.append(
            {
                "scenario_name": name,
                "description": cfg["description"].strip(),
                "population_series": cfg["population_series"],
                "per_capita_demand_tier": cfg["per_capita_demand"],
                "per_capita_l_per_day": per_capita_l_per_day,
                "climate_time_slice": climate_cfg["time_slice"],
                "climate_scenario": climate_cfg["scenario"],
                "rainfall_replay_type": replay_cfg["type"],
                "rainfall_replay_start_year": replay_cfg.get("start_year"),
                "rainfall_replay_n_quarters": replay_cfg["n_quarters"],
                "n_analogues_in_fan": n_analogues,
                "safe_yield_ml_per_year": safe_yield,
                # The full, undecayed reference figure (today's conditions,
                # groundwater at its sourced ceiling) - available_yield now
                # genuinely varies year to year (see balance_rows'
                # groundwater_yield_ml_per_year), so this one scenario-level
                # number is a baseline to compare against, not a claim that
                # it holds for the whole scenario.
                "available_yield_ml_per_year": (
                    safe_yield + EXISTING_DESAL_RECYCLED_ML_PER_YEAR + GROUNDWATER_FULL_ML_PER_YEAR
                ),
                "balance_negative_year": balance_negative_year,
            }
        )
        log(
            f"scenario {name}: done - safe_yield={safe_yield:,.0f} ML/yr, "
            f"balance_negative_year={balance_negative_year}"
        )

    _land_parquet(pl.DataFrame(dim_rows), data_dir, "scenario_dim", dt)
    _land_parquet(pl.DataFrame(trajectory_rows), data_dir, "scenario_trajectory", dt)
    _land_parquet(pl.DataFrame(balance_rows), data_dir, "scenario_balance", dt)
    _land_parquet(pl.DataFrame(commit_by_rows), data_dir, "scenario_commit_by", dt)
    _land_parquet(pl.DataFrame(trigger_rows), data_dir, "scenario_trigger_crossings", dt)
    log(f"all {len(scenarios_config)} scenarios landed to dt={dt}")


if __name__ == "__main__":
    run_all(
        Path(os.environ.get("DBT_DUCKDB_PATH", "data/warehouse.duckdb")),
        Path(os.environ.get("DATA_DIR", "data")),
    )
