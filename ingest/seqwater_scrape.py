"""Seqwater historical dam-levels fetcher.

NOT a fallback/nice-to-have anymore - confirmed during recon (see
docs/decisions.md, "Seqwater's historic-dam-levels page has real inline data")
that https://www.seqwater.com.au/historic-dam-levels server-renders a
drupalSettings JSON blob (`seqw_dam_levels.historical`) with daily %/ML for
all 25 Seqwater-operated dams plus a precomputed "SEQ Water Grid" aggregate -
no JavaScript execution, no headless browser needed. This is the *only*
source found with real data for all 12 SEQ Water Grid dams; BOM only has it
for Somerset (see ingest/bom_kiwis.py / docs/decisions.md).

Known limitation: the page's default load only returns the last ~5 years
(the `historical_dam_storage_form`'s default start_date). The full range back
to 2008-07-01 exists (visible in the date picker's `min` attribute) but
requires replaying that form's Drupal AJAX submission - attempted during
recon, did not return the widened dataset in the time available. TODO-VERIFY
extend to the full 2008+ range; not blocking for now since 5 years of real
daily data per dam is already far more than BOM gave us for 11 of the 12 dams.
"""

from __future__ import annotations

import json
import re
from typing import Any

import polars as pl

from ingest.cache import Cache

HISTORICAL_URL = "https://www.seqwater.com.au/historic-dam-levels"

_SETTINGS_RE = re.compile(r'data-drupal-selector="drupal-settings-json">(.*?)</script>', re.DOTALL)


def fetch(source_config: dict[str, Any], cache: Cache) -> pl.DataFrame:
    """Single dispatcher for `kind: scrape` (see ingest/config.py's `resource`
    field) - both endpoints are the same source system, just two different
    pages, so this keeps "one fetcher per kind" true rather than adding a
    second `kind`."""
    resource = source_config["resource"]
    if resource == "historical":
        return fetch_dam_levels(source_config, cache)
    if resource == "snapshot":
        return fetch_current_snapshot(cache)
    raise ValueError(f"unknown seqwater resource: {resource!r}")


def fetch_dam_levels(source_config: dict[str, Any], cache: Cache) -> pl.DataFrame:
    """Long-format daily dam levels: one row per (date, dam_name).

    Includes the precomputed "SEQ Water Grid" aggregate as its own
    `dam_name` row (source's `g`/`l` fields) - this is the spec's headline
    metric, computed by Seqwater itself, not re-derived here. The "All Dams"
    aggregate (source's `c` field, all 25 dams including non-grid ones) is
    dropped - out of scope per SPEC.md's 12-dam grid definition.
    """
    html = cache.get_text(HISTORICAL_URL)
    settings = _extract_drupal_settings(html)
    historical = settings["seqw_dam_levels"]["historical"][0]
    series = historical["series"]
    data = historical["data"]

    rows: list[dict[str, Any]] = []
    for series_entry in series:
        name = series_entry["name"]
        if name == "All Dams":
            continue
        dam_name = "SEQ Water Grid" if name == "SEQ Water Grid" else name
        pct_key = series_entry["y"]
        ml_key = series_entry.get("l")
        for day in data:
            level_pct = day.get(pct_key)
            volume_ml = day.get(ml_key) if ml_key else None
            if level_pct is None and volume_ml is None:
                continue
            rows.append(
                {
                    "storage_date": day["ds"],  # "DD-MM-YYYY"
                    "dam_name": dam_name,
                    "level_pct": level_pct,
                    "volume_ml": volume_ml,
                    "source_id": series_entry.get("source"),
                }
            )

    return pl.DataFrame(rows).with_columns(
        pl.col("storage_date").str.to_date("%d-%m-%Y"),
    )


_DAM_NAME_RE = re.compile(r'<a href="/dams/[^"]+"[^>]*>([^<]+)</a>')
_SOURCE_ID_RE = re.compile(r"/historic-dam-levels#source=(\d+)")
_REDUCED_FSL_NOTE_RE = re.compile(
    r'<span class="damExtraComment">(.*?)</span>\s*</span>\s*</span>', re.DOTALL
)


def fetch_current_snapshot(cache: Cache) -> pl.DataFrame:
    """The live /dam-levels table: dam name, full supply volume (ML, i.e. the
    *current operating* FSL reference - already reduced where a reduction is
    in effect), current volume (ML), % full, any reduced-FSL notice text, and
    the source id linking to the historical series. Used to populate
    seeds/dam_metadata.csv's FSL columns with real figures instead of
    TODO-VERIFY, and to cross-reference `source_id` in the historical fetch.
    """
    html = cache.get_text("https://www.seqwater.com.au/dam-levels")
    start = html.find('<table class="dam-levels-table')
    end = html.find("</table>", start) + len("</table>")
    table_html = html[start:end]

    rows: list[dict[str, Any]] = []
    for row_html in re.findall(r"<tr>(.*?)</tr>", table_html, re.DOTALL):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row_html, re.DOTALL)
        if not cells:
            continue
        name_match = _DAM_NAME_RE.search(cells[0])
        source_match = _SOURCE_ID_RE.search(cells[0])
        note_match = _REDUCED_FSL_NOTE_RE.search(cells[0])
        cleaned_rest = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in cells[1:]]
        note_text = None
        if note_match:
            note_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", note_match.group(1))).strip()
        rows.append(
            {
                "dam_name": name_match.group(1).strip() if name_match else None,
                "source_id": source_match.group(1) if source_match else None,
                "full_supply_volume_ml": _parse_ml(cleaned_rest[0]),
                "current_volume_ml": _parse_ml(cleaned_rest[1]),
                "current_pct_full": _parse_pct(cleaned_rest[2]),
                "comment": cleaned_rest[4] if len(cleaned_rest) > 4 else None,
                "reduced_fsl_note": note_text,
            }
        )
    return pl.DataFrame(rows)


def _parse_ml(text: str) -> float | None:
    digits = re.sub(r"[^\d.]", "", text)
    return float(digits) if digits else None


def _parse_pct(text: str) -> float | None:
    digits = re.sub(r"[^\d.]", "", text)
    return float(digits) if digits else None


def _extract_drupal_settings(html: str) -> dict[str, Any]:
    match = _SETTINGS_RE.search(html)
    if not match:
        raise RuntimeError(
            "drupal-settings-json blob not found - Seqwater's page structure may have "
            "changed; see docs/decisions.md for the shape this was built against"
        )
    return json.loads(match.group(1))
