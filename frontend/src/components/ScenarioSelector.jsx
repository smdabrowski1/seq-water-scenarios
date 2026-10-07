// Same dropdown pattern as the dam picker in App.jsx, but scenario names
// aren't self-explanatory like dam names - shows the selected scenario's
// real description underneath, not just the name.
export default function ScenarioSelector({ scenarios, selectedName, onSelect }) {
  const selected = scenarios?.find((s) => s.scenario_name === selectedName);

  return (
    <div className="scenario-select-label">
      <label className="dam-select-label">
        Scenario
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
function formatScenarioName(name) {
  return name
    .split("_")
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}
