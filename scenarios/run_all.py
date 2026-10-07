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
    find_balance_negative_year,
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
# GL/yr -> ML/yr, see seed_supply_options' existing rows
EXISTING_CLIMATE_INDEPENDENT_SUPPLY_ML_PER_YEAR = (43 + 16 + 59) * 1000


def _land_parquet(df: pl.DataFrame, data_dir: Path, name: str, dt: str) -> None:
    partition_dir = data_dir / "scenarios" / name / f"dt={dt}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    final_path = partition_dir / f"{name}.parquet"
    tmp_path = partition_dir / f".tmp-{name}.parquet"
    df.write_parquet(tmp_path)
    os.replace(tmp_path, final_path)


def run_all(warehouse_path: Path, data_dir: Path, log_cb=None) -> None:
    log = log_cb or print
    dt = datetime.now(UTC).strftime("%Y-%m-%d")

    con = duckdb.connect(str(warehouse_path), read_only=True)
    try:
        rainfall_rows = con.execute(
            "select rainfall_date, dam_name, rainfall_mm from fct_dam_rainfall_daily"
        ).fetchall()
        rainfall = pl.DataFrame(
            rainfall_rows, schema=["rainfall_date", "dam_name", "rainfall_mm"], orient="row"
        )
        quarterly_regional = quarterly_regional_rainfall(rainfall)

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
            "select option_name, lead_time_years from seed_supply_options"
        ).fetchall()
        supply_options = pl.DataFrame(
            supply_rows, schema=["option_name", "lead_time_years"], orient="row"
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
        available_yield = safe_yield + EXISTING_CLIMATE_INDEPENDENT_SUPPLY_ML_PER_YEAR
        balance_negative_year = find_balance_negative_year(demand_curve, available_yield)
        commit_by = compute_commit_by_dates(balance_negative_year, supply_options)

        for analogue in fan:
            for offset, (q_start, rain, storage) in enumerate(
                zip(
                    analogue["quarter_starts"],
                    analogue["rainfall_mm"],
                    analogue["trajectory_ml"][1:],
                )
            ):
                # quarter_offset is what the dashboard actually plots against
                # (N quarters from today, mapped to a real future calendar
                # date downstream in dbt) - q_start (the real historical
                # calendar date the rainfall came from) is kept too, for
                # traceability back to "which real year is this quarter from."
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

        for row in demand_curve.iter_rows(named=True):
            surplus_deficit = available_yield - row["demand_ml_per_year"]
            balance_rows.append(
                {
                    "scenario_name": name,
                    "year": row["year"],
                    "population_total": row["population_total"],
                    "demand_ml_per_year": row["demand_ml_per_year"],
                    "safe_yield_ml_per_year": safe_yield,
                    "available_yield_ml_per_year": available_yield,
                    "surplus_deficit_ml_per_year": surplus_deficit,
                }
            )

        for option_name, commit_year in commit_by.items():
            lead_time = supply_options.filter(pl.col("option_name") == option_name)[
                "lead_time_years"
            ][0]
            commit_by_rows.append(
                {
                    "scenario_name": name,
                    "option_name": option_name,
                    "balance_negative_year": balance_negative_year,
                    "lead_time_years": lead_time,
                    "commit_by_year": commit_year,
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
                "available_yield_ml_per_year": available_yield,
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
