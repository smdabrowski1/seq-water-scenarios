import * as Plot from "@observablehq/plot";
import { useEffect, useRef } from "react";
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

export default function SupplyDemandBalanceChart({ balance }) {
  const chartRef = useRef(null);
  const plotRef = useRef(null);

  useEffect(() => {
    if (!balance?.length) return;

    const deficitYears = balance.filter((d) => d.surplus_deficit_ml_per_year < 0);
    const firstDeficitYear = deficitYears[0]?.year;
    const lastRow = balance[balance.length - 1];

    // Available yield varies a lot by scenario (~224k ML/yr for the
    // Millennium Drought Repeat vs. ~634k ML/yr for baseline) - a fixed
    // domain tuned for one scenario clips the other's yield line off the
    // top of the chart entirely (confirmed live: the blue line silently
    // vanished on baseline). Computed from the actual data instead, with
    // headroom for the end-of-line labels.
    const maxValue = Math.max(
      ...balance.map((d) => Math.max(d.demand_ml_per_year, d.available_yield_ml_per_year)),
    );
    const yMax = maxValue * 1.12;

    // Fixed pixel dy offsets, not data-driven - demand and available yield
    // often converge to nearly the same value right where the labels sit
    // (the last year plotted), so offsetting by the *data* gap isn't enough
    // to keep the two text labels from overlapping. A plain mark being
    // false/undefined in Plot's marks array throws ("invalid mark") rather
    // than being skipped like a falsy React child would be - confirmed live
    // (a scenario with no deficit years broke the whole chart until this was
    // filtered explicitly) - so conditional marks are built separately and
    // filtered, never inlined with `&&`.
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
      Plot.lineY(balance, { x: "year", y: "demand_ml_per_year", stroke: DEMAND_ORANGE, strokeWidth: 2 }),
      Plot.lineY(balance, {
        x: "year",
        y: "available_yield_ml_per_year",
        stroke: YIELD_BLUE,
        strokeWidth: 2,
      }),
      Plot.text([lastRow], {
        x: "year",
        y: "demand_ml_per_year",
        text: () => "Demand",
        fill: DEMAND_ORANGE,
        dx: 8,
        dy: -8,
        fontSize: 12,
        fontWeight: 600,
        textAnchor: "start",
      }),
      Plot.text([lastRow], {
        x: "year",
        y: "available_yield_ml_per_year",
        text: () => "Available yield",
        fill: YIELD_BLUE,
        dx: 8,
        dy: 10,
        fontSize: 12,
        fontWeight: 600,
        textAnchor: "start",
      }),
      firstDeficitYear != null &&
        Plot.ruleX([firstDeficitYear], { stroke: DEFICIT_RED, strokeDasharray: "2,2" }),
      // Labelled near the x-axis, not the top-right corner - that's where
      // the series' own end-labels live, and the two collided there before.
      // Right-aligned (text extends *left* of the rule), not left-aligned -
      // the rule itself is often close to the chart's right edge, and a
      // left-aligned label there runs straight into the margin (confirmed
      // live - "balance-negative: 20" got clipped mid-digit).
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
      Plot.tip(
        balance,
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
      marginRight: 112,
      x: { label: "Year", tickFormat: "d" },
      y: { label: "ML / year", grid: true, domain: [0, yMax] },
      marks,
      style: { fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif" },
    });
    swapPlot(chartRef.current, plotRef, plot);
  }, [balance]);

  return <div ref={chartRef} className="chart-panel chart-panel-balance" />;
}
