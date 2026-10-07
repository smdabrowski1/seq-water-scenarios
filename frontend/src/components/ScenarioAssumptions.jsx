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
  );
}

function formatPeople(value) {
  return `${(value / 1e6).toFixed(2)}M people`;
}
