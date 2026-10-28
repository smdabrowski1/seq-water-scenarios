import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchDamTimeseries,
  fetchDams,
  fetchGridTimeseries,
  fetchScenarioBalance,
  fetchScenarioDetail,
  fetchScenarioTrajectory,
  fetchScenarios,
} from "./api.js";
import ChartErrorBoundary from "./components/ChartErrorBoundary.jsx";
import DamCharts from "./components/DamCharts.jsx";
import DateRangeFilter, { filterByWindow } from "./components/DateRangeFilter.jsx";
import DateScrubber from "./components/DateScrubber.jsx";
import DemoDisclaimerModal from "./components/DemoDisclaimerModal.jsx";
import FloatingScenarioSwitcher from "./components/FloatingScenarioSwitcher.jsx";
import GridSummary from "./components/GridSummary.jsx";
import MapView from "./components/MapView.jsx";
import ScenarioAssumptions from "./components/ScenarioAssumptions.jsx";
import ScenarioSelector from "./components/ScenarioSelector.jsx";
import ScenarioTrajectoryChart from "./components/ScenarioTrajectoryChart.jsx";
import SectionNav from "./components/SectionNav.jsx";
import SupplyDemandBalanceChart from "./components/SupplyDemandBalanceChart.jsx";

const VALID_SECTIONS = ["observed", "scenarios"];

function sectionFromHash() {
  const id = window.location.hash.replace("#", "");
  return VALID_SECTIONS.includes(id) ? id : "observed";
}

export default function App() {
  // Two top-level sections, reflected in the URL hash (#observed/#scenarios)
  // so a link, refresh, or the browser's back/forward button lands on the
  // same section instead of just in-memory tab state.
  const [activeSection, setActiveSection] = useState(sectionFromHash);

  useEffect(() => {
    const onHashChange = () => setActiveSection(sectionFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const selectSection = (id) => {
    window.location.hash = id;
    setActiveSection(id);
    // A major navigation change, unlike switching dams/scenarios within a
    // section (which must NOT scroll - see below) - landing on a new
    // section at the top is the expected behaviour here.
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const [dams, setDams] = useState(null);
  const [gridRows, setGridRows] = useState(null);
  const [selectedDam, setSelectedDam] = useState("Somerset");
  const [damRows, setDamRows] = useState(null);
  const [error, setError] = useState(null);
  // null/null = the full available window (storage data only spans ~5 years
  // total, so this is already the "5 years to most recent" view). Both ends
  // are independently settable: the dropdown picks a whole year, the dual
  // scrubber below opens any custom window.
  const [windowStart, setWindowStart] = useState(null);
  const [windowEnd, setWindowEnd] = useState(null);

  const [scenarios, setScenarios] = useState(null);
  const [selectedScenario, setSelectedScenario] = useState("millennium_drought_repeat_unrestricted");
  const [scenarioDetail, setScenarioDetail] = useState(null);
  const [scenarioTrajectory, setScenarioTrajectory] = useState(null);
  const [scenarioBalance, setScenarioBalance] = useState(null);

  // The main scenario picker is up near the top of a long page - the
  // balance chart's investment toggles and breakdown live well below it,
  // so switching scenarios while looking at those means a scroll all the
  // way back up. A floating switcher fills that gap, but only once the
  // real picker has actually scrolled out of view (tracked here, not in
  // the floating component itself, since it needs a ref to the real one).
  const scenarioSelectorRef = useRef(null);
  const [scenarioSelectorVisible, setScenarioSelectorVisible] = useState(true);
  useEffect(() => {
    if (activeSection !== "scenarios" || !scenarioSelectorRef.current) return;
    const observer = new IntersectionObserver(([entry]) => setScenarioSelectorVisible(entry.isIntersecting), {
      threshold: 0,
    });
    observer.observe(scenarioSelectorRef.current);
    return () => observer.disconnect();
  }, [activeSection, scenarios]);

  useEffect(() => {
    fetchDams().then(setDams).catch((e) => setError(String(e)));
    fetchGridTimeseries().then(setGridRows).catch((e) => setError(String(e)));
  }, []);

  // Scenario data loads lazily, the first time the Scenarios section is
  // visited - most sessions may never open it, no reason to fetch it
  // upfront. Fetched once; switching back and forth afterward reuses
  // what's already in state. The demo disclaimer rides the same "first
  // visit" guard instead of its own flag, since it's the same moment -
  // shown once per session, not on every return trip to this section.
  const scenariosLoadStarted = useRef(false);
  const [showDemoDisclaimer, setShowDemoDisclaimer] = useState(false);
  useEffect(() => {
    if (activeSection !== "scenarios" || scenariosLoadStarted.current) return;
    scenariosLoadStarted.current = true;
    setShowDemoDisclaimer(true);
    fetchScenarios().then(setScenarios).catch((e) => setError(String(e)));
  }, [activeSection]);

  useEffect(() => {
    setDamRows(null);
    fetchDamTimeseries(selectedDam)
      .then(setDamRows)
      .catch((e) => setError(String(e)));
  }, [selectedDam]);

  // Deliberately does NOT null the previous scenario's data before the new
  // fetch resolves - same root issue as the date-slider scroll jump (see
  // plotUtils.js's swapPlot): clearing state first unmounts every
  // conditionally-rendered chart/panel below, the section's height
  // collapses to zero for a moment, and everything after it visibly jumps.
  // Keeping the previous scenario's content mounted and swapping it in
  // place once the new data lands avoids that collapse - the charts' own
  // swapPlot then handles the redraw smoothly, same as switching dams or
  // dragging the scrubber. Out-of-order responses (rapid scenario
  // switching) are guarded with a ref instead of a state null-out.
  const latestScenarioRequest = useRef(null);
  const loadedScenarioRef = useRef(null);

  useEffect(() => {
    // Gated on the Scenarios section being open too, not just a scenario
    // being selected - selectedScenario already has a default value at
    // mount, so without this check it would fetch immediately on first
    // load even if the user never opens the Scenarios section.
    if (!selectedScenario || activeSection !== "scenarios") return;
    // Already have this exact scenario's data loaded (e.g. the user left
    // the section and came back without changing the selection) - skip the
    // redundant re-fetch.
    if (loadedScenarioRef.current === selectedScenario) return;
    const requestId = selectedScenario;
    latestScenarioRequest.current = requestId;
    loadedScenarioRef.current = requestId;

    fetchScenarioDetail(selectedScenario)
      .then((data) => {
        if (latestScenarioRequest.current === requestId) setScenarioDetail(data);
      })
      .catch((e) => setError(String(e)));
    fetchScenarioTrajectory(selectedScenario)
      .then((data) => {
        if (latestScenarioRequest.current === requestId) setScenarioTrajectory(data);
      })
      .catch((e) => setError(String(e)));
    fetchScenarioBalance(selectedScenario)
      .then((data) => {
        if (latestScenarioRequest.current === requestId) setScenarioBalance(data);
      })
      .catch((e) => setError(String(e)));
  }, [selectedScenario, activeSection]);

  const damNames = dams?.features.map((f) => f.properties.dam_name).sort() ?? [];
  const allDates = useMemo(() => gridRows?.map((r) => r.date) ?? [], [gridRows]);
  const effectiveWindowStart = windowStart ?? allDates[0] ?? null;
  const effectiveWindowEnd = windowEnd ?? allDates[allDates.length - 1] ?? null;

  const handleWindowChange = (start, end) => {
    setWindowStart(start);
    setWindowEnd(end);
  };

  return (
    <div className="app">
      <header className="app-header">
        <h1>
          SEQ <span className="app-header-accent">Water</span> Security
        </h1>
        <p className="app-subtitle">Dam levels and rainfall data across 12 SEQ locations</p>
      </header>

      {error && <div className="error-banner">{error}</div>}

      {showDemoDisclaimer && (
        <DemoDisclaimerModal onClose={() => setShowDemoDisclaimer(false)} />
      )}

      <SectionNav activeSection={activeSection} onSelect={selectSection} />

      {/* Both sections stay mounted once rendered, toggled via `hidden`
          instead of conditionally rendered/unmounted - MapView owns a real
          MapLibre GL instance with its own expensive init effect, and
          unmounting it on every section switch would re-initialise the map
          (and re-fetch its tiles) every time the user came back. */}
      <section hidden={activeSection !== "observed"} aria-labelledby="observed-heading">
        <h2 id="observed-heading" className="visually-hidden">
          Current &amp; History
        </h2>

        {/* Sits above every chart it drives (the grid-storage trend below,
            plus both dam charts further down) instead of trailing after
            the dam charts - a shared filter reads as global when it's
            positioned before the content it controls. */}
        <div className="date-scrubber-card card">
          <div className="date-scrubber-card-header">
            <span className="date-scrubber-card-label">Date range</span>
            <DateRangeFilter
              allDates={allDates}
              windowStart={effectiveWindowStart}
              windowEnd={effectiveWindowEnd}
              onChange={handleWindowChange}
            />
          </div>
          <DateScrubber
            allDates={allDates}
            windowStart={effectiveWindowStart}
            windowEnd={effectiveWindowEnd}
            onChange={handleWindowChange}
          />
        </div>

        {gridRows && (
          <ChartErrorBoundary>
            <GridSummary
              allRows={gridRows}
              windowStart={effectiveWindowStart}
              windowEnd={effectiveWindowEnd}
            />
          </ChartErrorBoundary>
        )}

        <main className="main-grid">
          <div className="map-column card">
            {dams && (
              <MapView dams={dams} selectedDam={selectedDam} onSelectDam={setSelectedDam} />
            )}
            {/* The OpenStreetMap/CARTO attribution this data's ODbL licence
                requires stays on the map itself (MapLibre's own built-in
                corner control, bottom-right - auto-rendered by the library,
                not this markup) - this is just the usage hint now, not a
                second copy of the legal notice. */}
            <div className="map-caption">
              <span className="map-caption-icon" aria-hidden="true">
                i
              </span>
              <p>Click a dam on the map to see its storage and rainfall history.</p>
            </div>
          </div>
          <div className="detail-column card">
            <label className="dam-select-label">
              <span>Dam</span>
              <select value={selectedDam} onChange={(e) => setSelectedDam(e.target.value)}>
                {damNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            {damRows && (
              <ChartErrorBoundary key={selectedDam}>
                <DamCharts
                  rows={filterByWindow(damRows, effectiveWindowStart, effectiveWindowEnd)}
                />
              </ChartErrorBoundary>
            )}
          </div>
        </main>
      </section>

      <section
        className="scenarios-section"
        hidden={activeSection !== "scenarios"}
        aria-labelledby="scenarios-heading"
      >
        <h2 id="scenarios-heading" className="visually-hidden">
          Scenarios
        </h2>

        <div className="scenario-controls-card card" ref={scenarioSelectorRef}>
          {scenarios && (
            <ScenarioSelector
              scenarios={scenarios}
              selectedName={selectedScenario}
              onSelect={setSelectedScenario}
            />
          )}
          {scenarioDetail && scenarioBalance && (
            <ScenarioAssumptions dim={scenarioDetail.dim} balance={scenarioBalance} />
          )}
        </div>

        {scenarioTrajectory && (
          // No key tied to selectedScenario here - that would force a full
          // unmount/remount on every scenario change, the same height-
          // collapse-causes-scroll-jump problem fixed above. Staying
          // mounted lets the chart's own swapPlot handle the redraw in
          // place, same as the dam/date charts.
          <ChartErrorBoundary>
            <ScenarioTrajectoryChart
              observed={scenarioTrajectory.observed}
              projected={scenarioTrajectory.projected}
            />
          </ChartErrorBoundary>
        )}
        {scenarioBalance && (
          <ChartErrorBoundary>
            <SupplyDemandBalanceChart
              balance={scenarioBalance}
              commitBy={scenarioDetail?.commitBy}
              dim={scenarioDetail?.dim}
            />
          </ChartErrorBoundary>
        )}
      </section>

      {activeSection === "scenarios" && scenarios && !scenarioSelectorVisible && (
        <FloatingScenarioSwitcher
          scenarios={scenarios}
          selectedName={selectedScenario}
          onSelect={setSelectedScenario}
        />
      )}
    </div>
  );
}
