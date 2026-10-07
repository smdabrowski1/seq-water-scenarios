import * as Plot from "@observablehq/plot";
import { useEffect, useRef } from "react";
import { swapPlot } from "../plotUtils.js";

// One unified "KPI hero" card - an eyebrow label, the headline stat (today's
// real reading, independent of whatever window the chart is scrubbed to),
// and the average over the currently selected range, in one flowing header
// row, then the trend chart spans the card's full width underneath. The
// date-range selector itself now lives on the date-range card above (it
// drives this chart along with the dam charts further down, so it belongs
// with the shared control, not duplicated here) - this card's right-hand
// slot holds a second stat instead.

const dateFormatter = new Intl.DateTimeFormat("en-AU", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

// Shared by both the "as of" and "selected range" stats so an up/down delta
// always reads the same way wherever it appears on this card.
function TrendChip({ trend, suffix }) {
  if (!trend) return null;
  return (
    <span className={`stat-trend ${trend.isRising ? "is-up" : "is-down"}`}>
      <svg
        viewBox="0 0 12 12"
        width="9"
        height="9"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <path
          d={trend.isRising ? "M2 9L10 2M10 2H5M10 2V7" : "M2 2L10 9M10 9H5M10 9V4"}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      {Math.abs(trend.delta).toFixed(1)}% {suffix}
    </span>
  );
}

export default function GridSummary({ allRows, windowStart, windowEnd }) {
  const chartRef = useRef(null);
  const plotRef = useRef(null);

  // Real readings only (skips gap rows) - both the headline stat and its
  // week-on-week trend chip need an actual prior reading to compare against,
  // not just "whatever's 7 rows back" if there happen to be gaps in between.
  const readings = allRows?.filter((r) => !r.is_gap && r.grid_storage_pct != null) ?? [];
  const latest = readings.length ? readings[readings.length - 1] : null;

  const windowed = readings.filter(
    (r) => (!windowStart || r.date >= windowStart) && (!windowEnd || r.date <= windowEnd),
  );
  const average = windowed.length
    ? windowed.reduce((sum, r) => sum + r.grid_storage_pct, 0) / windowed.length
    : null;

  let trend = null;
  if (latest) {
    const weekAgoCutoff = new Date(latest.date);
    weekAgoCutoff.setDate(weekAgoCutoff.getDate() - 7);
    const weekAgo = [...readings]
      .reverse()
      .find((r) => new Date(r.date) <= weekAgoCutoff);
    if (weekAgo) {
      const delta = latest.grid_storage_pct - weekAgo.grid_storage_pct;
      // Rising storage is the reassuring direction here (more water in the
      // grid), so the trend chip's colour follows that, not a generic
      // "up is green" convention.
      trend = { delta, isRising: delta >= 0 };
    }
  }

  // The average's own comparison is against the other stat on this card
  // (today's actual reading) rather than some third number - the two chips
  // read as "here's today, here's the range average, here's how they
  // differ", directly tying the two halves of this header together.
  let avgTrend = null;
  if (average != null && latest) {
    const delta = average - latest.grid_storage_pct;
    avgTrend = { delta, isRising: delta >= 0 };
  }

  useEffect(() => {
    if (!readings.length) return;

    const data = readings;
    const highlight = windowStart && windowEnd ? [{ x1: windowStart, x2: windowEnd }] : [];

    const plot = Plot.plot({
      width: chartRef.current.clientWidth || 900,
      height: 220,
      marginLeft: 48,
      x: { type: "utc", label: null },
      y: { label: null, grid: true, domain: [0, 105] },
      marks: [
        Plot.ruleY([0]),
        Plot.areaY(data, { x: "date", y: "grid_storage_pct", fill: "#2a78d6", fillOpacity: 0.1 }),
        Plot.lineY(data, { x: "date", y: "grid_storage_pct", stroke: "#2a78d6", strokeWidth: 2 }),
        Plot.rectY(highlight, {
          x1: "x1",
          x2: "x2",
          y1: 0,
          y2: 105,
          fill: "#2a78d6",
          fillOpacity: 0.12,
        }),
        Plot.tip(
          data,
          Plot.pointerX({
            x: "date",
            y: "grid_storage_pct",
            title: (d) => `${d.date}\n${d.grid_storage_pct.toFixed(1)}% full`,
          }),
        ),
      ],
      style: { fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif" },
    });
    swapPlot(chartRef.current, plotRef, plot);
  }, [allRows, windowStart, windowEnd]);

  return (
    <section className="grid-summary card">
      <div className="grid-summary-header">
        <span className="grid-summary-eyebrow">
          <span className="grid-summary-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
              <path
                d="M12 3C12 3 5 11.5 5 15.5C5 19.09 8.13 22 12 22C15.87 22 19 19.09 19 15.5C19 11.5 12 3 12 3Z"
                strokeLinejoin="round"
              />
            </svg>
          </span>
          Water Grid Storage (%)
        </span>

        <div className="grid-summary-stat">
          <span className="stat-value">
            {latest ? `${latest.grid_storage_pct.toFixed(1)}%` : "-"}
          </span>
          {latest && (
            <div className="stat-meta">
              <span className="stat-asof">
                <span className="stat-asof-dot" aria-hidden="true" />
                as of {dateFormatter.format(new Date(latest.date))}
              </span>
              <TrendChip trend={trend} suffix="vs last week" />
            </div>
          )}
        </div>

        <div className="grid-summary-stat grid-summary-stat-end">
          <span className="stat-value">{average != null ? `${average.toFixed(1)}%` : "-"}</span>
          {average != null && (
            <div className="stat-meta is-end">
              <span className="stat-asof">avg. selected range</span>
              <TrendChip trend={avgTrend} suffix="vs current" />
            </div>
          )}
        </div>
      </div>

      <div ref={chartRef} className="chart-panel grid-chart" />

      <div className="chart-note">
        <span className="chart-note-icon" aria-hidden="true">
          i
        </span>
        <p>Hover over the chart to see the total storage by date across all the locations.</p>
      </div>
    </section>
  );
}
