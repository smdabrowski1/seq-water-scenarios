"""DuckDB access layer.

Mirrors the Hobby CDM Project's `engine.py` concurrency pattern: FastAPI runs
sync route handlers on a thread pool, but a single shared DuckDB connection
isn't safe for concurrent `execute()` calls from multiple threads - so every
query grabs `self.con.cursor()` at the top rather than using `self.con`
directly. Read-only against the warehouse; nothing here ever writes - that's
`warehouse/orchestrator.py`'s job, run separately via `make refresh`.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import duckdb

WAREHOUSE_PATH = os.environ.get("WAREHOUSE_PATH", "data/warehouse.duckdb")


class Store:
    def __init__(self, warehouse_path: str = WAREHOUSE_PATH) -> None:
        if not Path(warehouse_path).exists():
            raise RuntimeError(
                f"{warehouse_path} not found - run `make refresh` first to build the warehouse"
            )
        self.con = duckdb.connect(warehouse_path, read_only=True)
        self.con.execute("INSTALL spatial")
        self.con.execute("LOAD spatial")

    def dams_geojson(self) -> dict[str, Any]:
        """One GeoJSON feature per dam: geometry + latest known level/capacity,
        so the map can render and color without a second request."""
        cur = self.con.cursor()
        rows = cur.execute("""
            select
                d.dam_name,
                d.current_fsl_ml,
                d.has_reduced_fsl,
                d.reduced_fsl_note,
                st_asgeojson(st_geomfromtext(d.geom_wkt)) as geom_geojson,
                f.storage_date as latest_date,
                f.storage_level_pct as latest_pct,
                f.storage_volume_ml as latest_volume_ml
            from dim_dam as d
            left join fct_dam_storage_daily as f
                on d.dam_name = f.dam_name
                and f.storage_date = (
                    select max(storage_date) from fct_dam_storage_daily as f2
                    where f2.dam_name = d.dam_name and not f2.is_gap
                )
            where d.geom_wkt is not null
            order by d.dam_name
        """).fetchall()
        cols = [c[0] for c in cur.description]

        import json

        features = []
        for row in rows:
            r = dict(zip(cols, row, strict=True))
            geom = json.loads(r.pop("geom_geojson"))
            latest_date = r.pop("latest_date")
            features.append(
                {
                    "type": "Feature",
                    "geometry": geom,
                    "properties": {
                        **r,
                        "latest_date": latest_date.isoformat() if latest_date else None,
                    },
                }
            )
        return {"type": "FeatureCollection", "features": features}

    def dam_names(self) -> list[str]:
        cur = self.con.cursor()
        rows = cur.execute("select dam_name from dim_dam order by dam_name").fetchall()
        return [r[0] for r in rows]

    def dam_timeseries(self, dam_name: str) -> list[dict[str, Any]]:
        cur = self.con.cursor()
        rows = cur.execute(
            """
            select
                s.storage_date as date,
                s.storage_level_pct,
                s.storage_volume_ml,
                s.is_gap,
                r.rainfall_mm
            from fct_dam_storage_daily as s
            left join fct_dam_rainfall_daily as r
                on s.dam_name = r.dam_name and s.storage_date = r.rainfall_date
            where s.dam_name = ?
            order by s.storage_date
            """,
            [dam_name],
        ).fetchall()
        cols = [c[0] for c in cur.description]
        return [_row_to_json_safe(dict(zip(cols, row, strict=True))) for row in rows]

    def grid_timeseries(self) -> list[dict[str, Any]]:
        cur = self.con.cursor()
        rows = cur.execute("""
            select storage_date as date, grid_storage_pct, grid_storage_volume_ml, is_gap
            from fct_grid_storage_daily
            order by storage_date
        """).fetchall()
        cols = [c[0] for c in cur.description]
        return [_row_to_json_safe(dict(zip(cols, row, strict=True))) for row in rows]

    def scenario_names(self) -> list[str]:
        cur = self.con.cursor()
        rows = cur.execute(
            "select scenario_name from dim_scenario order by scenario_name"
        ).fetchall()
        return [r[0] for r in rows]

    def scenario_list(self) -> list[dict[str, Any]]:
        """Powers the selector - every scenario's config + top-line result."""
        cur = self.con.cursor()
        rows = cur.execute("""
            select
                scenario_name, description, population_series, per_capita_demand_tier,
                climate_time_slice, climate_scenario, balance_negative_year
            from dim_scenario
            order by scenario_name
        """).fetchall()
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in rows]

    def scenario_detail(self, scenario_name: str) -> dict[str, Any]:
        """One dim_scenario row + its commit-by dates + its trigger crossings,
        bundled - all three are small, no reason for 3 round trips."""
        cur = self.con.cursor()
        dim_row = cur.execute(
            "select * from dim_scenario where scenario_name = ?", [scenario_name]
        ).fetchone()
        dim_cols = [c[0] for c in cur.description]
        dim = dict(zip(dim_cols, dim_row, strict=True))

        commit_by_rows = cur.execute(
            """
            select option_name, lead_time_years, commit_by_year
            from fct_commit_by_dates
            where scenario_name = ?
            order by option_name
            """,
            [scenario_name],
        ).fetchall()
        commit_by_cols = [c[0] for c in cur.description]
        commit_by = [dict(zip(commit_by_cols, row, strict=True)) for row in commit_by_rows]

        trigger_rows = cur.execute(
            """
            select trigger_name, trigger_pct, crossing_probability, expected_crossing_date
            from fct_trigger_crossings
            where scenario_name = ?
            order by trigger_pct desc
            """,
            [scenario_name],
        ).fetchall()
        trigger_cols = [c[0] for c in cur.description]
        triggers = [
            _row_to_json_safe(
                dict(zip(trigger_cols, row, strict=True)), date_key="expected_crossing_date"
            )
            for row in trigger_rows
        ]

        return {"dim": dim, "commitBy": commit_by, "triggers": triggers}

    def scenario_trajectory(self, scenario_name: str) -> dict[str, Any]:
        """The fan, plus a tail of real observed history to splice onto -
        avoids a second fetch or client-side date-matching for what's
        otherwise one continuous chart."""
        cur = self.con.cursor()
        observed_rows = cur.execute("""
            select storage_date as date, grid_storage_pct, grid_storage_volume_ml
            from fct_grid_storage_daily
            where not is_gap
            order by storage_date desc
            limit 730
        """).fetchall()
        observed_cols = [c[0] for c in cur.description]
        observed = [
            _row_to_json_safe(dict(zip(observed_cols, row, strict=True)))
            for row in reversed(observed_rows)
        ]

        projected_rows = cur.execute(
            """
            select
                quarter_offset, projected_date as date, storage_p10_ml, storage_p50_ml,
                storage_p90_ml, n_analogues, any_beyond_validated_range
            from fct_scenario_trajectory
            where scenario_name = ?
            order by quarter_offset
            """,
            [scenario_name],
        ).fetchall()
        projected_cols = [c[0] for c in cur.description]
        projected = [
            _row_to_json_safe(dict(zip(projected_cols, row, strict=True))) for row in projected_rows
        ]

        return {"observed": observed, "projected": projected}

    def scenario_balance(self, scenario_name: str) -> list[dict[str, Any]]:
        cur = self.con.cursor()
        rows = cur.execute(
            """
            select
                year, population_total, demand_ml_per_year,
                available_yield_ml_per_year, surplus_deficit_ml_per_year
            from fct_supply_demand_balance
            where scenario_name = ?
            order by year
            """,
            [scenario_name],
        ).fetchall()
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in rows]


def _row_to_json_safe(row: dict[str, Any], date_key: str = "date") -> dict[str, Any]:
    if row.get(date_key) is not None:
        row[date_key] = row[date_key].isoformat()
    return row
