import InfoToggle from "./InfoToggle.jsx";

// Same dropdown pattern as the dam picker in App.jsx, but scenario names
// aren't self-explanatory like dam names - shows the selected scenario's
// real description underneath, not just the name.
export default function ScenarioSelector({ scenarios, selectedName, onSelect }) {
  const selected = scenarios?.find((s) => s.scenario_name === selectedName);

  return (
    <div className="scenario-select-label">
      {/* How the scenario engine works - sits right above the picker it
          explains, instead of as a loose subtitle disconnected from it. The
          one-line version stays visible; the full methodology/data/
          assumptions writeup is a click away (same expand-for-more pattern
          as the trajectory chart's "How to read this chart"). This absorbed
          the old standalone "Limitations & assumptions" panel that used to
          sit at the bottom of the page. */}
      <div className="scenario-methodology">
        <span className="scenario-methodology-icon" aria-hidden="true">
          i
        </span>
        <div>
          <p>
            Replayed historical rainfall, climate adjustment, population growth, and demand -
            combined into the year the system would need more supply, and by when a decision
            would need to be made.
          </p>
          <InfoToggle label="What's behind this, and what it assumes">
            <p>
              <strong>What a scenario is.</strong> Each of the 9 scenarios combines three
              independent assumptions: a real historical rainfall sequence, replayed forward
              from today's actual storage rather than fitted by a statistical model; an
              optional climate-change adjustment; and a population/demand assumption. Replaying
              real weather is deliberate - every path is explainable as "what if the next few
              years repeated 1999-2001", and the result is a spread of outcomes, not one
              falsely precise line.
            </p>
            <p>
              <strong>What it's showing.</strong> For each scenario: the year the SEQ Water
              Grid's supply would fall behind demand, the "commit-by" date for each supply
              option (that balance-negative year minus the option's lead time - the number a
              planner would actually act on), and the probability of crossing each of
              Seqwater's real drought-response trigger levels.
            </p>
            <p>
              <strong>The data behind it.</strong> Dam storage and rainfall come from the
              Bureau of Meteorology's Water Data Online API and the Queensland Government's
              SILO climate dataset (gap-filled daily rainfall back to 1889), landed in a DuckDB
              warehouse and modelled with dbt. Population projections (low/medium/high) are
              the Queensland Government Statistician's Office's own; rainfall-change
              projections come from the Queensland Future Climate Dashboard; drought-response
              thresholds and supply-option lead times are sourced from Seqwater's published
              Drought Response Plan and Water Security Program.
            </p>
            <p>
              <strong>What to keep in mind.</strong> Demand is derived (population &times; a
              fixed litres-per-person-per-day figure), not measured - retailer-level demand
              isn't publicly published. Desal and recycled water are treated as a fixed yearly
              total, not something that could be ramped up or down during a drought.
              Minjerribah groundwater is modelled to decay under drought (its real bore-level
              triggers are monitored by Seqwater), but the exact decay amounts are a reasoned
              assumption, not a sourced figure. The underlying storage model is validated
              against only the last
              ~5 years of real data, which never included a genuine drought - scenarios whose
              rainfall falls outside that range are flagged as extrapolation on the chart. And
              commit-by dates are planning-relevant signals ("roughly this timeframe"), not
              dates a construction contract should be signed against without further
              engineering study.
            </p>
          </InfoToggle>
        </div>
      </div>

      <label className="dam-select-label">
        <span>Scenario</span>
        <select value={selectedName ?? ""} onChange={(e) => onSelect(e.target.value)}>
          {scenarios?.map((s) => (
            <option key={s.scenario_name} value={s.scenario_name}>
              {formatScenarioName(s.scenario_name)}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <div className="scenario-description">
          <span className="scenario-description-icon" aria-hidden="true">
            i
          </span>
          <p>{selected.description}</p>
        </div>
      )}
    </div>
  );
}

// scenario_name is a stable snake_case id (dim_scenario's key, scenarios.yml's
// own naming) - this is purely a display transform, never used for lookups.
// Exported - the floating scenario switcher needs the exact same formatting.
export function formatScenarioName(name) {
  return name
    .split("_")
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}
