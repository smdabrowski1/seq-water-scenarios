"""`make ingest` entrypoint: fetch every configured source, dispatched by kind,
landing each as a date-partitioned raw parquet file.

Idempotent by construction: each partition is written via write-temp-then-
os.replace(), so re-running the same day overwrites that partition rather
than appending duplicate rows.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from ingest.bom_kiwis import fetch_timeseries
from ingest.cache import Cache
from ingest.config import SOURCES
from ingest.seqwater_scrape import fetch as fetch_seqwater
from ingest.silo import fetch_point_data

LogCallback = Callable[[str], None]

_FETCHERS = {
    "bom": fetch_timeseries,
    "silo": fetch_point_data,
    "scrape": fetch_seqwater,
}


def _land_partition(df: pl.DataFrame, data_dir: Path, source_name: str, dt: str) -> None:
    partition_dir = data_dir / "raw" / source_name / f"dt={dt}"
    partition_dir.mkdir(parents=True, exist_ok=True)
    final_path = partition_dir / f"{source_name}.parquet"
    tmp_path = partition_dir / f".tmp-{source_name}.parquet"
    df.write_parquet(tmp_path)
    os.replace(tmp_path, final_path)


def run_all(data_dir: Path, log_cb: LogCallback | None = None) -> None:
    log = log_cb or print
    dt = datetime.now(UTC).strftime("%Y-%m-%d")
    cache = Cache(data_dir / ".cache" / "http_cache.db")
    try:
        for source_name, source_config in SOURCES.items():
            fetcher = _FETCHERS[source_config["kind"]]
            try:
                df = fetcher(source_config, cache)
                _land_partition(df, data_dir, source_name, dt)
                log(f"{source_name}: landed {df.height} rows to dt={dt}")
            except Exception as exc:  # noqa: BLE001 - optional sources must not abort the run
                if source_config.get("optional"):
                    log(f"{source_name}: FAILED (optional, continuing) - {exc}")
                else:
                    raise
    finally:
        cache.close()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    run_all(Path(os.environ.get("DATA_DIR", "data")))
