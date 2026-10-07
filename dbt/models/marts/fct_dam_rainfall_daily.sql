-- Gold: daily rainfall (mm) per dam, ~40 years. Skips intermediate - unlike
-- the Seqwater dam-levels feed (25 dams needing scoping down to the 12-dam
-- grid), this source only ever contains our 12 configured locations, so
-- there's no join/scoping/gap-flagging work to do between staging and here.
select
    rainfall_date,
    dam_name,
    lat,
    lon,
    rainfall_mm,
    source_code
from {{ ref('stg_silo__rainfall') }}
order by rainfall_date, dam_name
