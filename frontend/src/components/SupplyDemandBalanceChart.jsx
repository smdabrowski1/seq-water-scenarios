import * as Plot from "@observablehq/plot";
import { useEffect, useRef, useState } from "react";
import { swapPlot } from "../plotUtils.js";

// The spec's "money shot": declining/flat yield vs. growing demand. Two real
// series need two distinct colors + a legend (dataviz skill: "legend always
// present for >=2 series... direct-labeled"). Demand reuses the existing
// rainfall orange (a consistent "pressure/input" role); yield reuses the
// existing storage blue. The deficit region (demand > yield) is shaded with
// the real --danger hex (#d92d20, from styles.css - not resolved via
// var() here, same reason the chart tip CSS needed a hardcoded fallback
// this session: Plot renders raw SVG, which doesn't reliably inherit custom
// properties) - a real status-color use (highlighting a state), not a third
// series identity color.
const DEMAND_ORANGE = "#eb6834";
const YIELD_BLUE = "#2a78d6";
const DEFICIT_RED = "#d92d20";
const SELECTED_GRAY = "#4b4b4b";

function computeInvestableOptions(commitBy) {
  return (commitBy ?? []).filter((row) => {
    const leadTime = Number(row.lead_time_years);
    const yieldGl = Number(row.yield_gl_per_year);
    return row.commit_by_year != null && leadTime > 0 && Number.isFinite(yieldGl);
  });
}

// The breakdown's default year for a scenario, before any year's been
// clicked on the chart - the shortfall year is the obviously relevant one
// to start on when there is one, otherwise just the most recent year.
function deficitFallbackYear(balance) {
  return balance.find((d) => d.surplus_deficit_ml_per_year < 0)?.year ?? balance[balance.length - 1].year;
}

export default function SupplyDemandBalanceChart({ balance, commitBy, dim }) {
  const chartRef = useRef(null);
  const plotRef = useRef(null);
  // One on/off switch per real, costable investment - each toggle shows
  // its own effect independently by replacing the single yield line in
  // place (not stacking a second ghost line on top of it), which is what
  // "simulate this investment" actually means on a chart like this.
  const [enabledOptions, setEnabledOptions] = useState(() => new Set());
  // Which year the breakdown below is showing - null means "use this
  // scenario's own default" (computed fresh below), rather than storing
  // the default directly, so a scenario switch naturally falls back to its
  // own relevant year without needing an effect to recompute it.
  const [selectedYear, setSelectedYear] = useState(null);
  // Whether the breakdown is expanded or collapsed - deliberately NOT reset
  // on scenario change. If it's open, it stays open (now showing the new
  // scenario's breakdown); if it's collapsed, it stays collapsed - this is
  // a standing display preference, not per-scenario state.
  const [breakdownExpanded, setBreakdownExpanded] = useState(true);

  useEffect(() => {
    setEnabledOptions(new Set());
    setSelectedYear(null);
  }, [balance, commitBy]);

  const investableOptions = computeInvestableOptions(commitBy);
  const baselineHasDeficit = (balance ?? []).some((d) => d.surplus_deficit_ml_per_year < 0);
  const effectiveSelectedYear = selectedYear ?? deficitFallbackYear(balance ?? []);

  const toggleOption = (optionName) => {
    setEnabledOptions((prev) => {
      const next = new Set(prev);
      if (next.has(optionName)) next.delete(optionName);
      else next.add(optionName);
      return next;
    });
  };

  useEffect(() => {
    if (!balance?.length) return;

    // The single effective yield for each year, under whichever investments
    // are currently toggled on - this is the only yield figure the chart
    // ever shows. Starts from that YEAR's own available yield (not a flat
    // scenario-wide constant - groundwater's contribution genuinely varies
    // year to year, tracking the rainfall being replayed, see
    // scenarios/run_all.py). Multiple enabled investments stack on top
    // (each adds its own capacity from its own commit-by year), matching
    // how real supply options combine.
    const effectiveBalance = balance.map((d) => {
      let effectiveYield = d.available_yield_ml_per_year;
      for (const opt of investableOptions) {
        if (enabledOptions.has(opt.option_name) && d.year >= opt.commit_by_year) {
          effectiveYield += Number(opt.yield_gl_per_year) * 1000;
        }
      }
      return {
        ...d,
        available_yield_ml_per_year: effectiveYield,
        surplus_deficit_ml_per_year: effectiveYield - d.demand_ml_per_year,
      };
    });

    const deficitYears = effectiveBalance.filter((d) => d.surplus_deficit_ml_per_year < 0);
    const firstDeficitYear = deficitYears[0]?.year;

    const maxValue = Math.max(
      ...effectiveBalance.map((d) => Math.max(d.demand_ml_per_year, d.available_yield_ml_per_year)),
    );
    const yMax = maxValue * 1.12;

    // A plain mark being false/undefined in Plot's marks array throws
    // ("invalid mark") rather than being skipped like a falsy React child
    // would be - confirmed live earlier this session - so conditional marks
    // are built separately and filtered, never inlined with `&&`.
    const marks = [
      Plot.ruleY([0]),
      deficitYears.length > 0 &&
        Plot.areaY(deficitYears, {
          x: "year",
          y1: "available_yield_ml_per_year",
          y2: "demand_ml_per_year",
          fill: DEFICIT_RED,
          fillOpacity: 0.15,
        }),
      Plot.lineY(effectiveBalance, {
        x: "year",
        y: "demand_ml_per_year",
        stroke: DEMAND_ORANGE,
        strokeWidth: 2,
      }),
      Plot.lineY(effectiveBalance, {
        x: "year",
        y: "available_yield_ml_per_year",
        stroke: YIELD_BLUE,
        strokeWidth: 2,
      }),
      firstDeficitYear != null &&
        Plot.ruleX([firstDeficitYear], { stroke: DEFICIT_RED, strokeDasharray: "2,2" }),
      firstDeficitYear != null &&
        Plot.text([{ year: firstDeficitYear, label: `balance-negative: ${firstDeficitYear}` }], {
          x: "year",
          y: yMax * 0.04,
          text: "label",
          fill: DEFICIT_RED,
          dx: -6,
          fontSize: 11,
          textAnchor: "end",
        }),
      // Visual feedback for whichever year the breakdown panel below is
      // currently showing - a plain neutral rule, not competing with the
      // red/orange/blue already carrying real meaning on this chart.
      Plot.ruleX([effectiveSelectedYear], { stroke: SELECTED_GRAY, strokeWidth: 1.5 }),
      Plot.tip(
        effectiveBalance,
        Plot.pointerX({
          x: "year",
          y: "demand_ml_per_year",
          title: (d) =>
            `${d.year}\nDemand: ${Math.round(d.demand_ml_per_year).toLocaleString()} ML\nAvailable yield: ${Math.round(d.available_yield_ml_per_year).toLocaleString()} ML\n${d.surplus_deficit_ml_per_year >= 0 ? "Surplus" : "Deficit"}: ${Math.round(Math.abs(d.surplus_deficit_ml_per_year)).toLocaleString()} ML`,
        }),
      ),
    ].filter(Boolean);

    const plot = Plot.plot({
      width: chartRef.current.clientWidth || 900,
      height: 260,
      marginLeft: 56,
      marginRight: 24,
      x: { label: null, tickFormat: "d" },
      y: { label: null, grid: true, domain: [0, yMax] },
      marks,
      style: { fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif" },
    });

    // Click a year directly on the chart to show its breakdown below -
    // converts the click's screen position into SVG user-space via
    // getScreenCTM() (accounts for the SVG's responsive viewBox scaling),
    // then the x scale's own invert to go from pixel position back to a
    // year, snapped to the nearest real data point. Also expands the
    // breakdown if it was collapsed - clicking a year is a clear "show me
    // this" action.
    const svgNode = plot.tagName === "FIGURE" ? plot.querySelector("svg") : plot;
    const xScale = plot.scale("x");
    const years = effectiveBalance.map((d) => d.year);
    svgNode.style.cursor = "pointer";
    svgNode.addEventListener("click", (event) => {
      const pt = svgNode.createSVGPoint();
      pt.x = event.clientX;
      pt.y = event.clientY;
      const local = pt.matrixTransform(svgNode.getScreenCTM().inverse());
      const clickedYear = xScale.invert(local.x);
      const nearestYear = years.reduce((closest, year) =>
        Math.abs(year - clickedYear) < Math.abs(closest - clickedYear) ? year : closest,
      );
      setSelectedYear(nearestYear);
      setBreakdownExpanded(true);
    });

    swapPlot(chartRef.current, plotRef, plot);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [balance, commitBy, enabledOptions, effectiveSelectedYear]);

  return (
    <section className="scenario-chart-card card">
      <span className="chart-eyebrow">
        <span className="chart-eyebrow-icon chart-eyebrow-icon-balance" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
            <path
              d="M12 3v18M7 7l-4 7a4 4 0 0 0 8 0l-4-7ZM17 7l-4 7a4 4 0 0 0 8 0l-4-7Z"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        Supply vs. Demand (ML/year)
      </span>

      {/* A fixed legend, not end-of-line text labels - those collide
          whenever the two series converge in value (confirmed live: demand
          catching up to available yield pushed "Demand"/"Available yield"
          on top of each other, unreadable). A legend's position never
          depends on where the data happens to be, so it can't collide
          regardless of how the lines move. */}
      <div className="chart-legend">
        <span className="chart-legend-item">
          <span className="chart-legend-dot" style={{ background: DEMAND_ORANGE }} aria-hidden="true" />
          Demand
        </span>
        <span className="chart-legend-item">
          <span className="chart-legend-dot" style={{ background: YIELD_BLUE }} aria-hidden="true" />
          Available yield
        </span>
      </div>

      <div ref={chartRef} className="chart-panel chart-panel-balance" />

      <div className="chart-note">
        <span className="chart-note-icon" aria-hidden="true">
          i
        </span>
        <p>
          Hover for exact figures, or click a year on the chart to see that year's supply
          breakdown below.
          {baselineHasDeficit && investableOptions.length > 0
            ? " Toggle an investment below to see its effect on the yield line directly."
            : ""}
        </p>
      </div>

      {/* Three distinct states, deliberately not blended into one: a
          scenario with headroom the whole way through says so plainly and
          stops there; a scenario with a real shortfall and a real, costable
          option to fix it gets an actual switch (the chart's own yield line
          moves when you flip it, not a second overlaid line); any option
          whose capacity genuinely isn't published yet stays in the detail
          list below rather than getting a toggle it can't honestly power. */}
      {!baselineHasDeficit && (
        <div className="investment-status investment-status-ok">
          <span className="investment-status-icon" aria-hidden="true">
            <svg viewBox="0 0 20 20" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 10.5l4 4 8-9" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <p>No investment needed - available yield covers demand throughout this scenario.</p>
        </div>
      )}

      {baselineHasDeficit && investableOptions.length > 0 && (
        <div className="investment-toggle-row">
          {investableOptions.map((opt) => (
            <InvestmentToggle
              key={opt.option_name}
              option={opt}
              checked={enabledOptions.has(opt.option_name)}
              onChange={() => toggleOption(opt.option_name)}
              balance={balance}
            />
          ))}
        </div>
      )}

      {/* Always present, not something you have to open - a permanent
          fixture under the chart and its investment toggles, not above
          them. Only whether it's expanded or collapsed is a user choice,
          and that choice is a standing preference (see breakdownExpanded
          above), not scenario state. */}
      <YieldBreakdownPanel
        year={effectiveSelectedYear}
        balance={balance}
        dim={dim}
        commitBy={commitBy}
        investableOptions={investableOptions}
        enabledOptions={enabledOptions}
        expanded={breakdownExpanded}
        onToggleExpanded={() => setBreakdownExpanded((e) => !e)}
      />
    </section>
  );
}

// A real switch (track + thumb), not a bare checkbox - this is a
// "simulate this" control, not a settings preference, so it should read as
// an action with visible weight. Computes and shows its own plain-English
// outcome right next to it, independent of the chart's own labelling.
function InvestmentToggle({ option, checked, onChange, balance }) {
  const addedMlPerYear = Number(option.yield_gl_per_year) * 1000;
  const firstDeficitYear = balance.find((d) => d.surplus_deficit_ml_per_year < 0)?.year;

  let outcome = null;
  if (checked && firstDeficitYear != null) {
    const committed = balance.map((d) => ({
      year: d.year,
      effectiveYield: d.available_yield_ml_per_year + (d.year >= option.commit_by_year ? addedMlPerYear : 0),
      demand: d.demand_ml_per_year,
    }));
    const stillDeficitYear = committed.find((d) => d.demand > d.effectiveYield)?.year ?? null;
    if (stillDeficitYear == null) {
      outcome = { text: "Resolves the shortfall", tone: "good" };
    } else if (stillDeficitYear > firstDeficitYear) {
      outcome = { text: `Pushes the shortfall to ${stillDeficitYear}`, tone: "good" };
    } else {
      outcome = { text: `Doesn't prevent the ${firstDeficitYear} shortfall - arrives too late`, tone: "neutral" };
    }
  }

  return (
    <div className="investment-toggle">
      <label className="investment-switch">
        <input type="checkbox" checked={checked} onChange={onChange} />
        <span className="investment-switch-track">
          <span className="investment-switch-thumb" />
        </span>
      </label>
      <div className="investment-toggle-text">
        <span className="investment-toggle-label">{option.option_name}</span>
        <span className="investment-toggle-meta">
          +{option.yield_gl_per_year} GL/yr, commit by {option.commit_by_year}
        </span>
        {outcome && (
          <span className={`investment-toggle-outcome is-${outcome.tone}`}>{outcome.text}</span>
        )}
      </div>
    </div>
  );
}

// Fixed categorical colors, assigned by source kind, never cycled - a
// viewer should be able to learn "blue = dams, teal = desal" once and have
// it hold across every year/scenario they open the breakdown for.
const BREAKDOWN_COLORS = {
  dams: "#2a78d6",
  desalination: "#0d9488",
  recycled: "#7c5cbf",
  groundwater: "#c9980f",
  investment: "#16a34a",
};

function componentKind(label) {
  const lower = label.toLowerCase();
  if (lower.includes("dam")) return "dams";
  if (lower.includes("desalination")) return "desalination";
  if (lower.includes("recycled")) return "recycled";
  if (lower.includes("groundwater")) return "groundwater";
  return "investment";
}

// Every component here is real, sourced data - the dam figure is never the
// seed's nominal 478 GL/yr entitlement (that's a different number, a water
// plan allocation ceiling, not what the water-balance model actually found
// sustainable for this scenario's rainfall) - it's the scenario's own
// modelled `safe_yield_ml_per_year`, the same figure the chart's "Available
// yield" line is built from. Desal and recycled water are fixed constants
// the engine adds on top, so their seed figures are the real number.
// Groundwater is neither - it's a third, genuinely time-varying kind of
// component (see scenarios/run_all.py), read straight from this year's own
// `balance` row rather than a flat seed figure. This is why the
// breakdown's total always matches the chart's yield line exactly for this
// year - same per-year inputs, same arithmetic, just itemised.
function YieldBreakdownPanel({
  year,
  balance,
  dim,
  commitBy,
  investableOptions,
  enabledOptions,
  expanded,
  onToggleExpanded,
}) {
  const row = balance?.find((d) => d.year === year);
  if (!row) return null;

  const existingSupply = (commitBy ?? []).filter((r) => Number(r.lead_time_years) === 0);
  const damsRow = existingSupply.find((r) => r.option_name.includes("SEQ Water Grid dams"));
  const groundwaterRow = existingSupply.find((r) => r.option_name.toLowerCase().includes("groundwater"));
  const otherExisting = existingSupply.filter((r) => r !== damsRow && r !== groundwaterRow);

  const components = [];
  if (dim?.safe_yield_ml_per_year != null) {
    components.push({
      label: damsRow?.option_name ?? "SEQ Water Grid dams (12 reservoirs)",
      detail: "modelled, rainfall-dependent",
      valueMl: dim.safe_yield_ml_per_year,
    });
  }
  // Groundwater isn't fixed like desal/recycled water - its figure here is
  // THIS year's own value (balance's own per-year groundwater_yield_ml_per_year,
  // not a flat scenario constant), tracking a trailing average of the
  // rainfall actually being replayed around this point. The % shown is
  // relative to the seed's sourced 16 GL/yr ceiling.
  if (groundwaterRow && row.groundwater_yield_ml_per_year != null) {
    const fullMl = Number(groundwaterRow.yield_gl_per_year) * 1000;
    const pct = fullMl > 0 ? Math.round((row.groundwater_yield_ml_per_year / fullMl) * 100) : null;
    components.push({
      label: groundwaterRow.option_name,
      detail:
        pct != null && pct < 100
          ? `modelled, rainfall-dependent (${pct}% of full yield this year - reasoned assumption, not a sourced curve)`
          : "modelled, rainfall-dependent (full yield this year)",
      valueMl: row.groundwater_yield_ml_per_year,
    });
  }
  for (const r of otherExisting) {
    if (r.yield_gl_per_year === "TODO-VERIFY") continue;
    components.push({
      label: r.option_name,
      detail: "existing, fixed",
      valueMl: Number(r.yield_gl_per_year) * 1000,
    });
  }
  for (const opt of investableOptions) {
    if (enabledOptions.has(opt.option_name) && year >= opt.commit_by_year) {
      components.push({
        label: opt.option_name,
        detail: `committed, from ${opt.commit_by_year}`,
        valueMl: Number(opt.yield_gl_per_year) * 1000,
      });
    }
  }

  const totalYield = components.reduce((sum, c) => sum + c.valueMl, 0);
  const demand = row.demand_ml_per_year;
  const surplusDeficit = totalYield - demand;
  // Headroom past whichever is larger, so the demand marker always lands
  // inside the track (even mid-deficit, where demand exceeds the bar's own
  // total) rather than being clipped off the end.
  const scaleMax = Math.max(totalYield, demand) * 1.05;
  const demandPct = Math.min(100, (demand / scaleMax) * 100);

  return (
    <div className="yield-breakdown">
      <button
        type="button"
        className="yield-breakdown-summary-row"
        onClick={onToggleExpanded}
        aria-expanded={expanded}
      >
        <span className="yield-breakdown-title">Supply breakdown - {year}</span>
        <span className="yield-breakdown-summary">
          <span
            className={`yield-breakdown-chip is-${surplusDeficit >= 0 ? "surplus" : "deficit"}`}
          >
            {surplusDeficit >= 0 ? "Surplus" : "Deficit"}{" "}
            {Math.round(Math.abs(surplusDeficit)).toLocaleString()} ML
          </span>
          <svg
            className={`yield-breakdown-chevron ${expanded ? "is-open" : ""}`}
            viewBox="0 0 16 16"
            width="14"
            height="14"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
          >
            <path d="M4 6l4 4 4-4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      </button>

      {/* Fully unmounted when collapsed, not just visually hidden - the
          CSS-only grid-rows collapse trick left a real, confirmed-live
          sliver of the bar peeking out from under the summary row no
          matter how it was tuned. A conditional render has no such leak:
          collapsed genuinely means nothing below the summary row exists. */}
      {expanded && (
        <div className="yield-breakdown-inner">
          {/* The composition itself, as one proportional bar - reads faster
              than a list of numbers alone, and the demand marker shows
              directly whether the stack actually clears it. */}
          <div className="yield-bar-wrap">
            <div className="yield-bar">
              {components.map((c) => (
                <span
                  key={c.label}
                  className="yield-bar-segment"
                  style={{
                    width: `${(c.valueMl / scaleMax) * 100}%`,
                    background: BREAKDOWN_COLORS[componentKind(c.label)],
                  }}
                  title={`${c.label}: ${Math.round(c.valueMl).toLocaleString()} ML`}
                />
              ))}
              <span className="yield-bar-demand-marker" style={{ left: `${demandPct}%` }} />
            </div>
            <span className="yield-bar-demand-label" style={{ left: `${demandPct}%` }}>
              Demand: {Math.round(demand).toLocaleString()} ML
            </span>
          </div>

          <ul className="yield-breakdown-list">
            {components.map((c) => (
              <li key={c.label}>
                <span className="yield-breakdown-swatch" aria-hidden="true">
                  <span
                    className="yield-breakdown-dot"
                    style={{ background: BREAKDOWN_COLORS[componentKind(c.label)] }}
                  />
                </span>
                <span className="yield-breakdown-label">
                  {c.label}
                  <span className="yield-breakdown-detail">{c.detail}</span>
                </span>
                <span className="yield-breakdown-value">
                  {Math.round(c.valueMl).toLocaleString()} ML
                </span>
              </li>
            ))}
          </ul>

          <div className="yield-breakdown-row yield-breakdown-total">
            <span>Total available yield</span>
            <span>{Math.round(totalYield).toLocaleString()} ML</span>
          </div>
          <div className="yield-breakdown-row">
            <span>Demand</span>
            <span>{Math.round(demand).toLocaleString()} ML</span>
          </div>
        </div>
      )}
    </div>
  );
}
