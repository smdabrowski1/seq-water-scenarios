"""Climate adjustment: scales a rainfall series by the sourced % change for a
given time slice + emissions scenario, per SPEC.md section 6.2 ("scale
rainfall, then recompute runoff - do not scale storage directly"). Figures
come from `seed_climate_projections` (real SEQ regional figures - see
docs/decisions.md, 2026-10-02 entry).
"""

from __future__ import annotations

import polars as pl

# "none" is a real, distinct choice (no adjustment - the baseline rainfall
# sequence as observed), not a missing-data sentinel.
NO_ADJUSTMENT = "none"


def apply_climate_adjustment(
    rainfall_mm: pl.Series,
    climate_projections: pl.DataFrame,
    time_slice: int | None,
    scenario: str,
) -> pl.Series:
    """Scale a rainfall series (e.g. one column of quarterly regional mm
    values) by `seed_climate_projections.rainfall_pct_change`, matched on
    (time_slice, scenario). Returns the series unchanged if `scenario` is
    `NO_ADJUSTMENT`.
    """
    if scenario == NO_ADJUSTMENT:
        return rainfall_mm

    match = climate_projections.filter(
        (pl.col("time_slice") == time_slice) & (pl.col("scenario") == scenario)
    )
    if match.height != 1:
        raise ValueError(
            f"expected exactly one seed_climate_projections row for "
            f"time_slice={time_slice!r}, scenario={scenario!r}, found {match.height}"
        )
    pct_change = match["rainfall_pct_change"][0]
    return rainfall_mm * (1 + pct_change / 100)
