-- Silver: light typing/renaming only, over a committed static GeoJSON file
-- (reference/dam_boundaries.geojson), not a daily ingest source - dam
-- boundaries don't change day to day, so this was fetched once (OpenStreetMap,
-- via Nominatim's polygon_geojson - see docs/decisions.md for the real
-- per-dam source names/OSM ids) and committed instead of re-fetched on every
-- `make ingest` run. Visualization only - see docs/decisions.md on why this
-- project doesn't attempt flow/gradient hydrology modeling.
select
    dam_name,
    geom,
    osm_type,
    osm_id
from st_read('reference/dam_boundaries.geojson')
