"""SILO (Long Paddock) DataDrill point API fetcher.

SILO warns its gap-filled data isn't suitable for climate-change detection
studies - use for catchment rainfall history only, never to claim a trend.

Notes from checking the live endpoint (see docs/decisions.md for detail):
- No registration actually required - `username`/`password` aren't verified
  (SILO's own docs suggest 'apirequest' as an example password). A real email
  is used anyway.
- `DataDrillDataset.php` interpolates from SILO's 5km grid at any `lat`/`lon`
  (nearest 0.05 degree) - not tied to a real weather station. CATCHMENT_LOCATIONS
  below are real sourced coordinates (BOM gauge where one exists, otherwise
  OpenStreetMap Nominatim) - see docs/decisions.md for the source per dam.
- Units are millimetres.
- The `source` code in each day's response is unverified - SILO's docs pages
  for it 404'd. Landed as-is; don't assume what it means.
"""

from __future__ import annotations

import os
from typing import Any

import polars as pl

from ingest.cache import Cache

BASE_URL = "https://www.longpaddock.qld.gov.au/cgi-bin/silo/DataDrillDataset.php"

# Real, sourced coordinates for each SEQ Water Grid dam - see docs/decisions.md
# for which source (BOM gauge vs. OpenStreetMap Nominatim) confirmed each one.
CATCHMENT_LOCATIONS: list[dict[str, Any]] = [
    {"dam_name": "Wivenhoe", "lat": -27.39638889, "lon": 152.60222222, "source": "BOM"},
    {"dam_name": "Somerset", "lat": -27.11666667, "lon": 152.55444444, "source": "BOM"},
    {"dam_name": "North Pine", "lat": -27.2640909, "lon": 152.9368607, "source": "OSM"},
    {"dam_name": "Hinze", "lat": -28.05638889, "lon": 153.285, "source": "BOM"},
    {"dam_name": "Baroon Pocket", "lat": -26.7035831, "lon": 152.86434883, "source": "BOM"},
    {"dam_name": "Leslie Harrison", "lat": -27.5308122, "lon": 153.1812324, "source": "OSM"},
    {"dam_name": "Ewen Maddock", "lat": -26.7764888, "lon": 153.0068145, "source": "OSM"},
    {"dam_name": "Cooloolabin", "lat": -26.5446299, "lon": 152.8826585, "source": "OSM"},
    {"dam_name": "Sideling Creek", "lat": -27.2345215, "lon": 152.9566991, "source": "OSM"},
    {"dam_name": "Lake Macdonald", "lat": -26.3812145, "lon": 152.9300119, "source": "OSM"},
    {"dam_name": "Little Nerang", "lat": -28.07555556, "lon": 153.30527778, "source": "BOM"},
    {"dam_name": "Wappa", "lat": -26.5709432, "lon": 152.9201991, "source": "OSM"},
]

HISTORY_START = "19860101"  # ~40 years - covers the Millennium Drought and the
# 2011/2022 floods (the analogue years we care about). Short of SILO's full
# 1889+ depth; widen if needed.


def fetch_point_data(source_config: dict[str, Any], cache: Cache) -> pl.DataFrame:
    """Daily rainfall (mm) at each SEQ dam's real, sourced coordinates - long
    format, one row per (date, dam_name)."""
    api_key = os.environ.get("SILO_API_KEY")
    if not api_key:
        raise RuntimeError(
            "SILO_API_KEY not set - put a real email in .env (see .env.example); "
            "SILO doesn't actually verify registration, but a real contact is used anyway"
        )

    finish = source_config.get("finish_date") or _today()
    rows: list[dict[str, Any]] = []
    for location in CATCHMENT_LOCATIONS:
        params = {
            "start": HISTORY_START,
            "finish": finish,
            "lat": location["lat"],
            "lon": location["lon"],
            "format": "json",
            "username": api_key,
            "password": "apirequest",
            "comment": "R",  # daily_rain
        }
        raw = cache.get(BASE_URL, params=params, ttl=20 * 3600)
        for day in raw.get("data", []):
            for variable in day.get("variables", []):
                rows.append(
                    {
                        "rainfall_date": day["date"],
                        "dam_name": location["dam_name"],
                        "lat": location["lat"],
                        "lon": location["lon"],
                        "rainfall_mm": variable["value"],
                        "source_code": variable["source"],
                    }
                )

    return pl.DataFrame(rows).with_columns(
        pl.col("rainfall_date").str.to_date("%Y-%m-%d"),
    )


def _today() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y%m%d")
