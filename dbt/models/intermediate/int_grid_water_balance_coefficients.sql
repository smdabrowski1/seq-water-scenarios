-- Silver: the fitted (alpha, beta) relating quarterly regional rainfall to
-- quarterly SEQ Water Grid total storage change. Supersedes an earlier
-- Somerset-only, per-dam-FSL-scaled version of this model - real diagnostic
-- testing (out-of-sample / leave-one-out cross-validation, not just in-sample
-- R^2) showed Somerset's own local rainfall explains essentially none of its
-- quarterly behaviour out of sample (best attempt: R^2 = -0.04 on a
-- regression, 0.06 on k-nearest-neighbour analog matching - both
-- statistically indistinguishable from "no real relationship"), most likely
-- because Somerset's level is substantially driven by deliberate operator
-- decisions (flood mitigation, transfers with Wivenhoe) rather than passive
-- catchment hydrology. The SEQ Grid *total* cancels those inter-dam transfers
-- out by construction (moving water between two grid dams doesn't change the
-- grid total), and genuinely validates: leave-one-out CV R^2 = 0.627 against
-- regional (all-12-catchment-average) rainfall. See docs/decisions.md for the
-- full comparison table across every approach tried.
--
-- One real limitation this doesn't fix: the Grid's own real history is only
-- ~5 years (2021-09-28 onward) and contains no drought - the fit validates
-- well *within* that rainfall range, but applying it to Millennium-Drought-
-- severity rainfall deficits is genuine extrapolation beyond any data this
-- was ever checked against. scenarios/ must flag this prominently for any
-- scenario whose rainfall falls outside the observed training range, not
-- just quote the in-range CV R^2 as if it covered every case.
with daily_regional_rainfall as (
    select rainfall_date, avg(rainfall_mm) as regional_rainfall_mm
    from {{ ref('stg_silo__rainfall') }}
    group by 1
),

joined as (
    select
        g.storage_date,
        g.grid_storage_volume_ml,
        r.regional_rainfall_mm
    from {{ ref('int_grid_storage_daily') }} as g
    left join daily_regional_rainfall as r
        on r.rainfall_date = g.storage_date
    where not g.is_gap
),

quarterly as (
    select
        date_trunc('quarter', storage_date) as quarter_start,
        arg_max(grid_storage_volume_ml, storage_date) as grid_storage_volume_ml,
        sum(regional_rainfall_mm) as regional_rainfall_mm,
        count(*) as days_in_quarter
    from joined
    group by 1
    having count(*) >= 60  -- drop partial first/last quarters
),

with_change as (
    select
        quarter_start,
        regional_rainfall_mm,
        grid_storage_volume_ml - lag(grid_storage_volume_ml) over (order by quarter_start) as change_ml
    from quarterly
)

select
    regr_slope(change_ml, regional_rainfall_mm) as beta_ml_per_mm,
    regr_intercept(change_ml, regional_rainfall_mm) as alpha_ml_per_quarter,
    regr_r2(change_ml, regional_rainfall_mm) as calibration_r_squared,
    count(*) as calibration_n_quarters,
    min(regional_rainfall_mm) as observed_min_quarterly_rainfall_mm,
    max(regional_rainfall_mm) as observed_max_quarterly_rainfall_mm
from with_change
where change_ml is not null
