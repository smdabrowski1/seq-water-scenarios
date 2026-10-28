"""BOM Water Data Online - Kisters KiWIS API fetcher.

No API key. Quirks found against the live endpoint (see docs/decisions.md,
docs/samples/bom_*.json):
- `BASE_URL` must be https - the documented http:// URL 301-redirects.
- getSiteList / getTimeseriesList both return `list[list[Any]]`: a header row
  (column names) followed by data rows - not a dict.
- getTimeseriesValues returns `list[dict]`, one dict per requested ts_id, each
  with a `data` key holding `[timestamp, value, quality_code]` row triples.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import polars as pl

from ingest.cache import Cache

BASE_URL = "https://www.bom.gov.au/waterdata/services"
# getTimeseriesValues with no from/to defaults to just "today" (usually still
# pending/null). Always pass an explicit range.
DEFAULT_HISTORY_TTL_SECONDS = 20 * 3600  # daily refresh cadence; don't re-pull all history hourly


def list_sites(cache: Cache, **filters: Any) -> list[list[Any]]:
    params = {
        "service": "kisters",
        "type": "queryServices",
        "request": "getSiteList",
        "format": "json",
        **filters,
    }
    return cache.get(BASE_URL, params=params)


def list_timeseries(cache: Cache, station_no: str, **filters: Any) -> list[list[Any]]:
    params = {
        "service": "kisters",
        "type": "queryServices",
        "request": "getTimeseriesList",
        "format": "json",
        "station_no": station_no,
        **filters,
    }
    return cache.get(BASE_URL, params=params)


def fetch_timeseries(station_config: dict[str, Any], cache: Cache) -> pl.DataFrame:
    """Fetch one station's timeseries values, typed as a Polars DataFrame.

    Requires an explicit from/to range (see DEFAULT_HISTORY_TTL_SECONDS above).
    `station_config["from_date"]` is required; `to_date` defaults to today (UTC).
    `cache_ttl_seconds` can override the default per source - a multi-decade
    history doesn't need a 20-hour cadence just to pick up one trailing day,
    and a longer TTL also means cached data keeps serving through a BOM outage.
    """
    to_date = station_config.get("to_date") or datetime.now(UTC).strftime("%Y-%m-%d")
    ttl = station_config.get("cache_ttl_seconds", DEFAULT_HISTORY_TTL_SECONDS)
    params = {
        "service": "kisters",
        "type": "queryServices",
        "request": "getTimeseriesValues",
        "format": "json",
        "ts_id": station_config["ts_id"],
        "from": station_config["from_date"],
        "to": to_date,
        "returnfields": "Timestamp,Value,Quality Code",
    }
    raw = cache.get(BASE_URL, params=params, ttl=ttl)
    rows = raw[0]["data"] if raw else []
    return pl.DataFrame(
        rows,
        schema={"timestamp": pl.String, "value": pl.Float64, "quality_code": pl.Int64},
        orient="row",
    ).with_columns(
        pl.col("timestamp").str.to_datetime("%Y-%m-%dT%H:%M:%S%.3f%:z", time_unit="ms"),
        pl.lit(station_config["station_no"]).alias("station_no"),
        pl.lit(station_config["ts_id"]).alias("ts_id"),
    )
