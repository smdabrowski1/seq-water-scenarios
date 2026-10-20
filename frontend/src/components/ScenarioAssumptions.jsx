import InfoToggle from "./InfoToggle.jsx";

// Makes the two demand-side assumptions explicit in real numbers, not just
// tier names - "medium population growth" and "status_quo demand" don't say
// anything on their own; the actual population trajectory and L/person/day
// figure are what the user asked to see spelled out.
const DEMAND_TIER_LABELS = {
  status_quo: "status quo",
  efficiency: "efficiency",
  drought_restricted: "drought-restricted",
};

const POPULATION_SERIES_LABELS = {
  low: "low",
  medium: "medium",
  high: "high",
};

export default function ScenarioAssumptions({ dim, balance }) {
  if (!dim || !balance?.length) return null;

  const firstYear = balance[0];
  const lastYear = balance[balance.length - 1];

  return (
    <div>
      <dl className="scenario-assumptions">
        <div className="scenario-assumption">
          <dt>Population growth</dt>
          <dd>
            {formatPeople(firstYear.population_total)} ({firstYear.year}) &rarr;{" "}
            {formatPeople(lastYear.population_total)} ({lastYear.year})
            <span className="scenario-assumption-tier">
              {" "}
              - {POPULATION_SERIES_LABELS[dim.population_series] ?? dim.population_series} series
            </span>
          </dd>
        </div>
        <div className="scenario-assumption">
          <dt>Per-person demand</dt>
          <dd>
            {dim.per_capita_l_per_day} L/person/day
            <span className="scenario-assumption-tier">
              {" "}
              - {DEMAND_TIER_LABELS[dim.per_capita_demand_tier] ?? dim.per_capita_demand_tier}
            </span>
          </dd>
        </div>
      </dl>

      {/* Scenario-specific assumptions, keyed on `dim` - re-expands with
          whatever's true for the currently selected scenario rather than a
          static list, since what rainfall basis/climate adjustment/supply
          figure applies genuinely changes scenario to scenario. */}
      <InfoToggle label="This scenario's assumptions">
        <p>
          <strong>Rainfall basis.</strong> {formatRainfallBasis(dim)}
        </p>
        <p>
          <strong>Climate adjustment.</strong> {formatClimateBasis(dim)}
        </p>
        <p>
          <strong>Available supply.</strong> Up to{" "}
          {Math.round(dim.available_yield_ml_per_year).toLocaleString()} ML/year - desal and
          recycled water are held fixed throughout, not ramped up or down during the scenario.
          Groundwater is the exception: it's modelled to decline as the replayed rainfall dries
          up and recover as it returns, rather than staying flat (see the supply breakdown
          below for the real figure in any given year).
        </p>
        <p>
          <strong>Demand.</strong> Per-person usage is held constant at{" "}
          {dim.per_capita_l_per_day} L/day for the whole scenario, rather than responding to
          restriction announcements day to day.
        </p>
      </InfoToggle>
    </div>
  );
}

function formatPeople(value) {
  return `${(value / 1e6).toFixed(2)}M people`;
}

function formatRainfallBasis(dim) {
  const years = Math.round(dim.rainfall_replay_n_quarters / 4);
  if (dim.rainfall_replay_type === "fixed") {
    const endYear = dim.rainfall_replay_start_year + years - 1;
    return `The real ${dim.rainfall_replay_start_year}-${endYear} rainfall sequence, replayed once forward from today's actual storage.`;
  }
  return `A rotating fan of ${dim.n_analogues_in_fan} real historical ${years}-year rainfall sequences, each replayed forward from today's actual storage.`;
}

function formatClimateBasis(dim) {
  if (!dim.climate_time_slice || dim.climate_scenario === "none") {
    return "None - today's observed rainfall sequence, unscaled.";
  }
  return `Queensland Future Climate ${dim.climate_scenario} rainfall adjustment, ${dim.climate_time_slice} time slice.`;
}
