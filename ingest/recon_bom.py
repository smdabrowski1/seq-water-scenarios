"""Recon script: hit BOM KiWIS once each for getSiteList/getTimeseriesList/
getTimeseriesValues and save the raw response for inspection.

Run manually: `uv run python -m ingest.recon_bom`

Throwaway-but-committed - kept as a reference for the actual response shape
under docs/samples/. Update docs/decisions.md with anything new observed.
"""

from __future__ import annotations

import json
from pathlib import Path

from ingest.bom_kiwis import list_sites, list_timeseries
from ingest.cache import Cache

SAMPLES_DIR = Path("docs/samples")


def main() -> None:
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    cache = Cache(Path("data/.cache/recon.db"))
    try:
        sites = list_sites(cache)
        _save("bom_getsitelist.json", sites)
        print(
            f"getSiteList: {len(sites) if isinstance(sites, list) else 'see file'} entries -> saved"
        )

        # TODO-VERIFY: replace with a real station_no found in the getSiteList response
        # above before running this a second time.
        station_no = "TODO-VERIFY"
        timeseries = list_timeseries(cache, station_no=station_no)
        _save("bom_gettimeserieslist.json", timeseries)
        print("getTimeseriesList -> saved")
    finally:
        cache.close()


def _save(filename: str, payload: object) -> None:
    (SAMPLES_DIR / filename).write_text(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
