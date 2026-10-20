import { formatScenarioName } from "./ScenarioSelector.jsx";

// A small floating control so switching scenarios doesn't mean scrolling
// all the way back up to the main picker - the balance chart's own
// investment toggles and breakdown live well below it on a long page. Only
// rendered once the real selector has scrolled out of view (App.jsx tracks
// that with an IntersectionObserver), so there's never two identical
// controls on screen at once.
export default function FloatingScenarioSwitcher({ scenarios, selectedName, onSelect }) {
  return (
    <div className="floating-scenario-switcher">
      <label className="floating-scenario-switcher-label">
        <span>Scenario</span>
        <select value={selectedName ?? ""} onChange={(e) => onSelect(e.target.value)}>
          {scenarios?.map((s) => (
            <option key={s.scenario_name} value={s.scenario_name}>
              {formatScenarioName(s.scenario_name)}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
