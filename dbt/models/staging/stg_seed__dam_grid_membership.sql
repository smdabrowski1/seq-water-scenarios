-- Silver: light typing/renaming only over the seeds/dam_grid_membership.csv
-- seed - the small set of facts that genuinely can't be scraped (BOM site-id
-- crosswalk, catchment) plus the 12-dam grid-membership flag itself.
select
    dam_name,
    cast(grid_member as boolean) as grid_member,
    bom_site_id,
    catchment,
    source_url,
    as_at_date
from {{ ref('dam_grid_membership') }}
