"""Static per-source configuration, dispatched by `kind`.

Translates the Hobby CDM Project's `backend/registry.py` pattern: one config dict
per data source (fetch params only) rather than one bespoke script per source. Each
`kind` has exactly one generic fetcher (`ingest/bom_kiwis.py`, `ingest/silo.py`,
`ingest/seqwater_scrape.py`); adding a new dam or station is a new dict entry, not
new code.

**Seqwater is the primary source for the 12-dam grid.** Confirmed during recon
(docs/decisions.md, "Seqwater's historic-dam-levels page has real inline
data") that Seqwater's own historic-dam-levels page server-renders real daily
%/ML for all 12 SEQ Water Grid dams plus a precomputed grid-total series - no
headless browser needed, a static-HTML fetch is enough.

BOM's Somerset-only cross-check sources were removed 2026-09-28 once this was
confirmed - a whole separate pipeline for one dam that Seqwater's own feed
already covers stopped earning its keep. The cross-check did catch one real,
now-documented finding (BOM's Somerset % is stale relative to Seqwater's own
reduced-FSL reference; the two sources' ML volumes agreed closely) - that
finding is preserved in docs/decisions.md, it didn't need the source to keep
running to stay true.

**Re-added 2026-10-04, for a different reason: scenario-engine calibration
- then superseded as the actual calibration source two days later, kept as
reference data regardless.** Somerset is the only one of the 12 grid dams
with real BOM storage history reaching back through the actual Millennium
Drought (1996-05-22 onward), so the first attempt at the water-balance model
(see scenarios/) fit rainfall-to-storage-change on Somerset alone. Real
out-of-sample validation (not just in-sample R^2) showed that relationship
has essentially no genuine predictive power (best attempt: out-of-sample
R^2 = -0.04) - Somerset's level turns out to be substantially driven by
operator decisions (flood mitigation, transfers with Wivenhoe), not passive
catchment hydrology. The model that actually validates
(`int_grid_water_balance_coefficients`, leave-one-out CV R^2 = 0.627) fits
the SEQ Grid *total* against regional rainfall instead - inter-dam transfers
cancel out at the grid level by construction. See docs/decisions.md for the
full comparison across every approach tried.

Kept in `SOURCES` anyway: it's real, genuinely-sourced historical data (the
only dam-level record spanning the actual drought), useful on its own for
plausibility-checking scenario output even though it isn't what the model is
fit on. Uses `value_ml` (BOM's volume column), not its `%` column, to
sidestep the known FSL-reference mismatch entirely. A long `cache_ttl_seconds`
is set deliberately - this is static historical data, not a freshness-critical
feed, and a long TTL also means an already-cached response keeps this source
usable through a live BOM outage (confirmed useful - BOM's API had a real
multi-hour, still-ongoing outage starting the same day this was added).
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
        # FSL/capacity reference data, fetched daily like everything else rather than
        # hand-transcribed into a seed - it changes rarely, but there's no reason a
        # rare change should require a manual CSV edit instead of just re-scraping.
        "optional": False,
    },
    "silo_catchment_rainfall": {
        "kind": "silo",
        # Locations are hardcoded in ingest/silo.py's CATCHMENT_LOCATIONS (real,
        # sourced coordinates for all 12 dams - see docs/decisions.md), not
        # here - unlike the BOM/Seqwater sources, this fetcher covers many
        # locations in one call, so there's nothing per-dam to configure.
        "optional": False,  # SILO_API_KEY is set - this is a real primary source now
    },
    "bom_somerset_storage_volume": {
        "kind": "bom",
        "station_no": "143305A",
        # DMQaQc.Merged.DailyMean.24HR, Storage Volume, ML - confirmed real, see docs/decisions.md
        "ts_id": "368803010",
        # real period of record starts 1996-05-22; a few months earlier is harmless (empty rows)
        "from_date": "1996-01-01",
        # Deliberately pinned, not left to default-to-today: `to_date` is part of
        # the cache key, so a dynamic "today" would cache-miss on every new day
        # regardless of cache_ttl_seconds - defeating the point of a long TTL the
        # moment BOM's API is unreachable (confirmed the hard way same day: a
        # 90-day TTL still couldn't serve the cached response because the `to`
        # param didn't match). This is a calibration snapshot, not a live feed -
        # bump this date by hand occasionally to pick up new trailing days, not
        # on every run.
        "to_date": "2026-09-28",
        "cache_ttl_seconds": 30 * 24 * 3600,  # 30 days - see module docstring
        # Optional: this is a calibration input, not something the dashboard's
        # headline series depends on - a BOM outage shouldn't fail the whole
        # pipeline the way a missing Seqwater/SILO source would.
        "optional": True,
    },
}


def sources_of_kind(kind: SourceKind) -> dict[str, dict[str, Any]]:
    return {name: cfg for name, cfg in SOURCES.items() if cfg["kind"] == kind}
