-- Gold: dam dimension. FSL/capacity fields come from the real, automated
-- Seqwater snapshot fetch (stg_seqwater__dam_fsl_snapshot), not a hand-keyed
-- seed - see seeds/README.md. Only bom_site_id/catchment (genuinely
-- unscrapeable) come from the small dam_grid_membership seed. `geom_wkt` is
-- the real reservoir boundary polygon (OpenStreetMap, via
-- reference/dam_boundaries.geojson - visualization only, see
-- docs/decisions.md) - not all dams may have one if the reference file is
-- ever regenerated without full coverage, hence the left join.
select
    d.dam_name,
    d.grid_member,
    d.bom_site_id,
    d.catchment,
    f.current_fsl_ml,
    f.has_reduced_fsl,
    f.reduced_fsl_note,
    st_astext(g.geom) as geom_wkt,
    g.osm_type as geom_osm_type,
    g.osm_id as geom_osm_id,
    d.source_url,
    d.as_at_date
from {{ ref('stg_seed__dam_grid_membership') }} as d
left join {{ ref('stg_seqwater__dam_fsl_snapshot') }} as f
    on d.dam_name = f.dam_name
left join {{ ref('stg_geo__dam_boundaries') }} as g
    on d.dam_name = g.dam_name
where d.grid_member
