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
import CommitByPanel from "./components/CommitByPanel.jsx";
import DamCharts from "./components/DamCharts.jsx";
import DateRangeFilter, { filterByWindow } from "./components/DateRangeFilter.jsx";
import DateScrubber from "./components/DateScrubber.jsx";
import GridSummary from "./components/GridSummary.jsx";
import LimitationsPanel from "./components/LimitationsPanel.jsx";
import MapView from "./components/MapView.jsx";
import ScenarioAssumptions from "./components/ScenarioAssumptions.jsx";
import ScenarioSelector from "./components/ScenarioSelector.jsx";
import ScenarioTrajectoryChart from "./components/ScenarioTrajectoryChart.jsx";
import SectionNav from "./components/SectionNav.jsx";
import SupplyDemandBalanceChart from "./components/SupplyDemandBalanceChart.jsx";
import TriggerCrossingsPanel from "./components/TriggerCrossingsPanel.jsx";

const VALID_SECTIONS = ["observed", "scenarios"];

function sectionFromHash() {
  const id = window.location.hash.replace("#", "");
  return VALID_SECTIONS.includes(id) ? id : "observed";
}

export default function App() {
  // Two top-level sections, reflected in the URL hash (#observed/#scenarios)
  // so a link, refresh, or the browser's back/forward button lands on the
  // same section - not just in-memory tab state.
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
    // section (which must NOT scroll - see the fixes below) - landing on a
    // new section at the top is the expected, helpful behaviour here.
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const [dams, setDams] = useState(null);
  const [gridRows, setGridRows] = useState(null);
  const [selectedDam, setSelectedDam] = useState("Somerset");
  const [damRows, setDamRows] = useState(null);
  const [error, setError] = useState(null);
  // null/null = the full available window (storage data only spans ~5 years
  // total, so this is already the "5 years to most recent" view). Both ends
  // are independently settable now (dropdown picks a whole year; the dual
  // scrubber below can open any custom window) rather than a fixed-length
  // window panned from a single end.
  const [windowStart, setWindowStart] = useState(null);
  const [windowEnd, setWindowEnd] = useState(null);

  const [scenarios, setScenarios] = useState(null);
  const [selectedScenario, setSelectedScenario] = useState("millennium_drought_repeat_unrestricted");
  const [scenarioDetail, setScenarioDetail] = useState(null);
  const [scenarioTrajectory, setScenarioTrajectory] = useState(null);
  const [scenarioBalance, setScenarioBalance] = useState(null);

  useEffect(() => {
    fetchDams().then(setDams).catch((e) => setError(String(e)));
    fetchGridTimeseries().then(setGridRows).catch((e) => setError(String(e)));
  }, []);

  // Scenario data loads lazily, the first time the Scenarios section is
  // actually visited - most sessions may never open it, no reason to fetch
  // it upfront on every page load. Fetched once; switching back and forth
  // afterward reuses what's already in state.
  const scenariosLoadStarted = useRef(false);
  useEffect(() => {
    if (activeSection !== "scenarios" || scenariosLoadStarted.current) return;
    scenariosLoadStarted.current = true;
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
  // collapses to zero for a moment, and everything after it on the page
  // visibly jumps. Keeping the previous scenario's content mounted and
  // swapping it in place once the new data lands avoids that collapse
  // entirely - the charts' own swapPlot then handles the redraw smoothly,
  // same as switching dams or dragging the scrubber already does. Guarded
  // against out-of-order responses (rapid scenario switching) with a ref,
  // not a state null-out.
  const latestScenarioRequest = useRef(null);
  const loadedScenarioRef = useRef(null);

  useEffect(() => {
    // Gated on the Scenarios section being open too, not just a scenario
    // being selected - selectedScenario already has a default value at
    // mount, so without this check it would fetch immediately on first
    // load even if the user never opens the Scenarios section at all.
    if (!selectedScenario || activeSection !== "scenarios") return;
    // Already have this exact scenario's data loaded (e.g. the user left
    // the section and came back without changing the selection) - skip the
    // redundant re-fetch rather than silently re-requesting identical data.
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
        <h1>SEQ Water Security</h1>
        <p className="app-subtitle">Dam levels and rainfall data across 12 SEQ locations</p>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <SectionNav activeSection={activeSection} onSelect={selectSection} />

      {/* Both sections stay mounted once rendered, toggled via `hidden`
          rather than conditionally rendered/unmounted - MapView owns a real
          MapLibre GL instance with its own expensive init effect, and
          unmounting it on every section switch would re-initialise the map
          (and re-fetch its tiles) every single time the user came back. */}
      <section hidden={activeSection !== "observed"} aria-labelledby="observed-heading">
        <h2 id="observed-heading" className="visually-hidden">
          Current &amp; History
        </h2>

        {/* Sits above every chart it drives (the grid-storage trend below,
            plus both dam charts further down) rather than trailing after
            the dam charts - a shared filter reads as global when it's
            positioned before the content it controls, not buried after
            some of it. */}
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
        className="scenarios-section card"
        hidden={activeSection !== "scenarios"}
        aria-labelledby="scenarios-heading"
      >
        <h2 id="scenarios-heading">Scenarios</h2>
        <p className="app-subtitle">
          Replayed historical rainfall, climate adjustment, population growth, and demand -
          combined into the year the system would need more supply, and by when a decision
          would need to be made.
        </p>
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
        {scenarioTrajectory && (
          // No key tied to selectedScenario here - that would force a full
          // unmount/remount on every scenario change (the same height-
          // collapse-causes-scroll-jump problem this effect was just fixed
          // for, one layer up). Staying mounted lets the chart's own
          // swapPlot handle the redraw in place, same as the dam/date charts.
          <ChartErrorBoundary>
            <ScenarioTrajectoryChart
              observed={scenarioTrajectory.observed}
              projected={scenarioTrajectory.projected}
            />
          </ChartErrorBoundary>
        )}
        {scenarioBalance && (
          <ChartErrorBoundary>
            <SupplyDemandBalanceChart balance={scenarioBalance} />
          </ChartErrorBoundary>
        )}
        {scenarioDetail && (
          <div className="scenario-panels-grid">
            <CommitByPanel commitBy={scenarioDetail.commitBy} />
            <TriggerCrossingsPanel triggers={scenarioDetail.triggers} />
          </div>
        )}
        {scenarioDetail && <LimitationsPanel />}
      </section>
    </div>
  );
}
