import * as Plot from "@observablehq/plot";
import { useEffect, useRef } from "react";
import { swapPlot } from "../plotUtils.js";

// Two small multiples sharing a time axis, not a dual-axis chart (SEQ Water
// Grid storage % and rainfall mm are different scales - see dataviz skill:
// "Two measures of different scale -> two charts, small multiples, or
// indexed to a common base", never two y-scales on one chart).
export default function DamCharts({ rows }) {
  const storageRef = useRef(null);
  const storagePlotRef = useRef(null);
  const rainfallRef = useRef(null);
  const rainfallPlotRef = useRef(null);

  useEffect(() => {
    if (!rows?.length) return;

    const storageData = rows.filter((r) => !r.is_gap && r.storage_level_pct != null);
    const plot = Plot.plot({
      width: storageRef.current?.clientWidth || 640,
      height: 200,
      marginLeft: 48,
      x: { type: "utc", label: null },
      y: { label: null, grid: true, domain: [0, 105] },
      marks: [
        Plot.ruleY([0]),
        Plot.lineY(storageData, {
          x: "date",
          y: "storage_level_pct",
          stroke: "#2a78d6",
          strokeWidth: 2,
        }),
        Plot.tip(
          storageData,
          Plot.pointerX({
            x: "date",
            y: "storage_level_pct",
            title: (d) => `${d.date}\n${d.storage_level_pct.toFixed(1)}% full`,
          }),
        ),
      ],
      style: { fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif" },
    });
    swapPlot(storageRef.current, storagePlotRef, plot);
  }, [rows]);

  useEffect(() => {
    if (!rows?.length) return;

    const rainfallData = rows.filter((r) => r.rainfall_mm != null);
    const plot = Plot.plot({
      width: rainfallRef.current?.clientWidth || 640,
      height: 160,
      marginLeft: 48,
      x: { type: "utc", label: null },
      y: { label: null, grid: true },
      marks: [
        Plot.ruleY([0]),
        // areaY/lineY, not barY/rectY - barY assumes a categorical (band)
        // x-scale, which conflicts with this chart's continuous "utc"
        // x-scale and throws ("scale incompatible with channel: utc !==
        // band"). rectY avoids that error but its `interval` option produced
        // a wrong y-axis (max 4,000mm against real data topping out at
        // ~209mm). Not worth chasing further either way - at ~1,829 days in
        // a ~640px panel, discrete bars wouldn't be legible at this zoom
        // level; a thin area reads better regardless.
        Plot.areaY(rainfallData, { x: "date", y: "rainfall_mm", fill: "#eb6834", fillOpacity: 0.5 }),
        Plot.lineY(rainfallData, { x: "date", y: "rainfall_mm", stroke: "#eb6834", strokeWidth: 1 }),
        Plot.tip(
          rainfallData,
          Plot.pointerX({
            x: "date",
            y: "rainfall_mm",
            title: (d) => `${d.date}\n${d.rainfall_mm.toFixed(1)}mm`,
          }),
        ),
      ],
      style: { fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif" },
    });
    swapPlot(rainfallRef.current, rainfallPlotRef, plot);
  }, [rows]);

  return (
    <div className="dam-charts">
      <span className="chart-eyebrow">
        <span className="chart-eyebrow-icon chart-eyebrow-icon-storage" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
            <path
              d="M12 3C12 3 5 11.5 5 15.5C5 19.09 8.13 22 12 22C15.87 22 19 19.09 19 15.5C19 11.5 12 3 12 3Z"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        Storage (%)
      </span>
      <div className="chart-panel chart-panel-storage">
        <div ref={storageRef} />
      </div>

      <span className="chart-eyebrow">
        <span className="chart-eyebrow-icon chart-eyebrow-icon-rainfall" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2">
            <path
              d="M7 15a4.5 4.5 0 0 1 .5-8.97A5.5 5.5 0 0 1 18 8.5a3.5 3.5 0 0 1-.5 6.98"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path d="M9 18.5l-1 2M13 18.5l-1 2M17 18.5l-1 2" strokeLinecap="round" />
          </svg>
        </span>
        Rainfall (mm/day)
      </span>
      <div className="chart-panel chart-panel-rainfall">
        <div ref={rainfallRef} />
      </div>

      <div className="chart-note">
        <span className="chart-note-icon" aria-hidden="true">
          i
        </span>
        <p>Hover over a chart to see storage and rainfall history by location.</p>
      </div>
    </div>
  );
}
