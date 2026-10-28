"""Static per-source configuration, dispatched by `kind`.

One config dict per data source (fetch params only), one generic fetcher per
`kind` (`ingest/bom_kiwis.py`, `ingest/silo.py`, `ingest/seqwater_scrape.py`).
Adding a dam or station is a new dict entry, not new code.

**Seqwater is the primary source for the 12-dam grid.** Its historic-dam-levels
page server-renders real daily %/ML for all 12 SEQ Water Grid dams plus a
precomputed grid-total series - no headless browser needed. See docs/decisions.md.

BOM's Somerset-only cross-check was dropped once that was confirmed - a separate
pipeline for one dam Seqwater's feed already covers wasn't worth keeping running.
It had already caught one real finding (BOM's Somerset % is stale relative to
Seqwater's reduced-FSL reference; ML volumes agreed closely), preserved in
docs/decisions.md.

Re-added later for scenario-engine calibration. Somerset is the only one of the
12 grid dams with BOM storage history reaching back through the Millennium
Drought (1996-05-22 onward), so the first water-balance model attempt fit
rainfall-to-storage-change on Somerset alone. Out-of-sample validation showed
no real predictive power there (R^2 = -0.04) - Somerset's level is driven
mostly by operator decisions (flood mitigation, transfers with Wivenhoe), not
catchment hydrology. The model that actually validates
(`int_grid_water_balance_coefficients`, leave-one-out CV R^2 = 0.627) fits the
SEQ Grid *total* against regional rainfall instead, since inter-dam transfers
cancel out at the grid level. Full comparison in docs/decisions.md.

Kept in `SOURCES` anyway as the only dam-level record spanning the actual
drought - useful for plausibility-checking scenario output even though it
isn't the calibration source. Uses `value_ml`, not `%`, to avoid the known
FSL-reference mismatch. Long `cache_ttl_seconds`: static historical data, and
a long TTL kept this source usable through a real multi-hour BOM outage.
"""

from __future__ import annotations

from typing import Any, Literal

SourceKind = Literal["bom", "silo", "scrape"]

SOURCES: dict[str, dict[str, Any]] = {
    "seqwater_dam_levels_historical": {
        "kind": "scrape",
        "resource": "historical",
        "optional": False,  # primary source for the 12-dam grid - see module docstring
    },
    "seqwater_dam_fsl_snapshot": {
        "kind": "scrape",
        "resource": "snapshot",
        # FSL/capacity reference data - scraped daily rather than hand-transcribed
        # into a seed, even though it changes rarely.
        "optional": False,
    },
    "silo_catchment_rainfall": {
        "kind": "silo",
        # Locations live in ingest/silo.py's CATCHMENT_LOCATIONS, not here - this
        # fetcher covers all 12 dams in one call, so nothing per-dam to configure.
        "optional": False,
    },
    "bom_somerset_storage_volume": {
        "kind": "bom",
        "station_no": "143305A",
        # DMQaQc.Merged.DailyMean.24HR, Storage Volume, ML - see docs/decisions.md
        "ts_id": "368803010",
        # period of record actually starts 1996-05-22; earlier rows are just empty
        "from_date": "1996-01-01",
        # Pinned, not "today": `to_date` is part of the cache key, so a moving
        # date would cache-miss daily and defeat the long TTL - exactly what
        # broke the cached fallback during a real BOM outage. Calibration
        # snapshot, not a live feed - bump by hand to pick up new trailing days.
        "to_date": "2026-09-28",
        "cache_ttl_seconds": 30 * 24 * 3600,  # 30 days - see module docstring
        # Calibration input, not part of the dashboard's headline series - a BOM
        # outage shouldn't fail the whole pipeline.
        "optional": True,
    },
}


def sources_of_kind(kind: SourceKind) -> dict[str, dict[str, Any]]:
    return {name: cfg for name, cfg in SOURCES.items() if cfg["kind"] == kind}
