"""Pipeline orchestrator: ingest -> dbt build -> dbt test -> promote.

Write to a temp path, validate, `os.replace()` into the live path, and only
then flip the registry — a failure before that last step leaves whatever is
currently live untouched.

dbt is pointed at the temp path via the `DBT_DUCKDB_PATH` env var
(dbt/profiles.yml.example reads it with a default), so a build-in-progress
never touches the warehouse file the dashboard export step reads from.
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

from warehouse import registry

logger = logging.getLogger(__name__)

LogCallback = Callable[[str], None]

DBT_PROJECT_DIR = "dbt"
DBT_PROFILES_DIR = "dbt"


def run_pipeline(data_dir: Path, warehouse_dir: Path, registry_db_path: Path) -> None:
    con = registry.connect(str(registry_db_path))
    try:
        registry.reap_stale_jobs(con)
        if registry.has_running_job(con):
            raise RuntimeError("pipeline already running")

        run_id = registry.new_run_id()
        registry.start_run(con, run_id)

        def log_cb(message: str) -> None:
            logger.info("[%s] %s", run_id, message)
            registry.append_log(con, run_id, message)

        warehouse_dir.mkdir(parents=True, exist_ok=True)
        # dbt-duckdb derives its catalog name from the file stem; a leading dot or
        # extra dots in that stem (e.g. ".tmp-<id>.duckdb") breaks that derivation.
        tmp_warehouse = warehouse_dir / f"tmp_{run_id}.duckdb"
        final_warehouse = warehouse_dir / "warehouse.duckdb"

        try:
            registry.set_status(con, run_id, "ingesting")
            _run_ingest(run_id, data_dir, log_cb)

            registry.set_status(con, run_id, "building")
            _run_dbt_build(tmp_warehouse, log_cb)

            registry.set_status(con, run_id, "scenario_engine")
            _run_scenario_engine(tmp_warehouse, data_dir, log_cb)
            _run_dbt_build_scenario_outputs(tmp_warehouse, log_cb)

            registry.set_status(con, run_id, "testing")
            _run_dbt_test(tmp_warehouse, log_cb)

            _validate_warehouse(tmp_warehouse)

            os.replace(tmp_warehouse, final_warehouse)
            registry.activate_run(con, run_id, warehouse_path=str(final_warehouse))
            log_cb("run activated")
        except Exception as exc:  # noqa: BLE001 - failure path deliberately catch-all
            registry.set_status(con, run_id, "failed", error=str(exc)[:2000])
            raise
        finally:
            tmp_warehouse.unlink(missing_ok=True)
    finally:
        con.close()


def _run_ingest(run_id: str, data_dir: Path, log_cb: LogCallback) -> None:
    """Fetch every configured source, dispatched by kind. Writes directly to
    data_dir/raw/ — per-source date partitions are independently idempotent, so
    this isn't gated behind warehouse promotion the way the dbt build is.
    """
    from ingest.run_all import run_all

    run_all(data_dir, log_cb)


def _run_dbt(args: list[str], tmp_warehouse: Path, log_cb: LogCallback) -> None:
    cmd = [
        "dbt",
        "--no-use-colors",
        *args,
        "--project-dir",
        DBT_PROJECT_DIR,
        "--profiles-dir",
        DBT_PROFILES_DIR,
    ]
    env = {**os.environ, "DBT_DUCKDB_PATH": str(tmp_warehouse)}
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    log_cb(result.stdout[-4000:])
    if result.returncode != 0:
        tail = result.stdout[-2000:]
        raise RuntimeError(f"{' '.join(cmd)} failed (exit {result.returncode}):\n{tail}")


def _run_dbt_build(tmp_warehouse: Path, log_cb: LogCallback) -> None:
    """Seed + run (models only, no tests) - kept separate from `dbt test` so the
    registry's building/testing status split means something.

    Excludes the `scenario_output`-tagged models (scenarios/'s own staging +
    marts) - those read parquet that scenarios/run_all.py hasn't written yet
    at this point in the pipeline (it runs *from* this build's own output -
    dim_dam, fct_dam_rainfall_daily, int_grid_water_balance_coefficients,
    etc.). See _run_dbt_build_scenario_outputs, which runs after the scenario
    engine, for the second half.
    """
    _run_dbt(["seed"], tmp_warehouse, log_cb)
    _run_dbt(["run", "--exclude", "tag:scenario_output"], tmp_warehouse, log_cb)


def _run_dbt_build_scenario_outputs(tmp_warehouse: Path, log_cb: LogCallback) -> None:
    """The other half of the build - runs after scenarios/run_all.py has
    written its parquet output, so these models' sources actually exist."""
    _run_dbt(["run", "--select", "tag:scenario_output"], tmp_warehouse, log_cb)


def _run_scenario_engine(tmp_warehouse: Path, data_dir: Path, log_cb: LogCallback) -> None:
    """Runs every named scenario (scenarios/config/scenarios.yml) against the
    just-built warehouse, landing results as raw parquet for
    _run_dbt_build_scenario_outputs to pick up. See scenarios/run_all.py."""
    from scenarios.run_all import run_all as run_scenarios

    run_scenarios(tmp_warehouse, data_dir, log_cb)


def _run_dbt_test(tmp_warehouse: Path, log_cb: LogCallback) -> None:
    _run_dbt(["test"], tmp_warehouse, log_cb)


_VALIDATE_TABLES = [
    "dim_dam",
    "int_storage_daily",
    "fct_dam_storage_daily",
    "fct_grid_storage_daily",
    "dim_scenario",
    "fct_scenario_trajectory",
]


def _validate_warehouse(tmp_warehouse: Path) -> None:
    """A dbt-test pass already validates model logic; this is the file-level
    check that the build actually produced usable tables.

    Checks one table from every layer (an intermediate model, not just the
    final marts) - a real bug (models materialized as views got their
    catalog name baked into the stored SQL at the temp path's name, breaking
    every view after the promote-time rename to the final path; see
    docs/decisions.md) passed the single-table check that used to be here
    because the one table checked happened to be immune to it.
    """
    import duckdb

    con = duckdb.connect(str(tmp_warehouse), read_only=True)
    try:
        for table in _VALIDATE_TABLES:
            (count,) = con.execute(f"select count(*) from {table}").fetchone()  # noqa: S608
            if count == 0:
                raise RuntimeError(f"{table} is empty after build")
    finally:
        con.close()


if __name__ == "__main__":
    import logging as _logging

    from dotenv import load_dotenv

    load_dotenv()
    _logging.basicConfig(level=_logging.INFO)

    run_pipeline(
        data_dir=Path(os.environ.get("DATA_DIR", "data")),
        warehouse_dir=Path(os.environ.get("WAREHOUSE_DIR", "data")),
        registry_db_path=Path(os.environ.get("REGISTRY_DB", "data/registry.db")),
    )
