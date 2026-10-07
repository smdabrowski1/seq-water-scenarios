import * as Plot from "@observablehq/plot";
import { useEffect, useRef } from "react";
import InfoToggle from "./InfoToggle.jsx";
import { swapPlot } from "../plotUtils.js";

// Real observed history (solid line) continuing into a simulated fan
// (shaded p10-p90 band + dashed p50 line) - same blue throughout (this is
// one metric, grid storage, not two different series; color follows the
// entity, not the observed/projected distinction - dataviz skill). The
// *style* change (solid -> dashed, line -> band) is what signals "this part
// is simulated," not a color change.
const STORAGE_BLUE = "#2a78d6";

export default function ScenarioTrajectoryChart({ observed, projected }) {
  const chartRef = useRef(null);
  const plotRef = useRef(null);

  useEffect(() => {
    if (!observed?.length || !projected?.length) return;

    const today = projected[0]?.date;
    // Lower band/line opacity once the replayed rainfall exceeds the
    // water-balance model's own validated range - a real, required
    // disclosure (see scenarios/LIMITATIONS.md), not decoration. The tip
    // below states this explicitly in words too - the visual cue alone
    // isn't treated as sufficient on its own.
    const projectedStyled = projected.map((d) => ({
      ...d,
      bandOpacity: d.any_beyond_validated_range ? 0.08 : 0.18,
      lineOpacity: d.any_beyond_validated_range ? 0.55 : 1,
    }));

    const plot = Plot.plot({
      width: chartRef.current.clientWidth || 900,
      height: 260,
      marginLeft: 56,
      x: { type: "utc", label: null },
      y: { label: "SEQ Water Grid storage (ML)", grid: true, domain: [0, 2300000] },
      marks: [
        Plot.ruleY([0]),
        Plot.lineY(observed, {
          x: "date",
          y: "grid_storage_volume_ml",
          stroke: STORAGE_BLUE,
          strokeWidth: 2,
        }),
        Plot.areaY(projectedStyled, {
          x: "date",
          y1: "storage_p10_ml",
          y2: "storage_p90_ml",
          fill: STORAGE_BLUE,
          fillOpacity: "bandOpacity",
        }),
        Plot.lineY(projectedStyled, {
          x: "date",
          y: "storage_p50_ml",
          stroke: STORAGE_BLUE,
          strokeWidth: 2,
          strokeOpacity: "lineOpacity",
          strokeDasharray: "5,3",
        }),
        Plot.ruleX([today], { stroke: "#6a6a6a", strokeDasharray: "2,2" }),
        Plot.text([{ date: today, label: "today" }], {
          x: "date",
          y: 2300000,
          text: "label",
          dy: 12,
          fill: "#6a6a6a",
          fontSize: 11,
        }),
        Plot.tip(
          observed,
          Plot.pointerX({
            x: "date",
            y: "grid_storage_volume_ml",
            title: (d) =>
              `${d.date}\n${Math.round(d.grid_storage_volume_ml).toLocaleString()} ML (${d.grid_storage_pct.toFixed(1)}% full)\nobserved`,
          }),
        ),
        Plot.tip(
          projectedStyled,
          Plot.pointerX({
            x: "date",
            y: "storage_p50_ml",
            title: (d) =>
              `${d.date}\nmedian: ${Math.round(d.storage_p50_ml).toLocaleString()} ML\nrange: ${Math.round(d.storage_p10_ml).toLocaleString()}-${Math.round(d.storage_p90_ml).toLocaleString()} ML (${d.n_analogues} replayed sequence${d.n_analogues === 1 ? "" : "s"})${d.any_beyond_validated_range ? "\n⚠ beyond the model's validated rainfall range" : ""}`,
          }),
        ),
      ],
      style: { fontFamily: "system-ui, -apple-system, 'Segoe UI', sans-serif" },
    });
    swapPlot(chartRef.current, plotRef, plot);
  }, [observed, projected]);

  return (
    <div>
      <div ref={chartRef} className="chart-panel chart-panel-scenario" />
      <InfoToggle label="How to read this chart">
        <p>
          <strong>Solid line:</strong> observed history. <strong>Shaded band + dashed line:</strong>{" "}
          simulated range across replayed historical rainfall sequences (p10-p90, median
          dashed). <strong>Faded sections</strong> exceed the water-balance model's own
          validated rainfall range - see scenarios/LIMITATIONS.md.
        </p>
      </InfoToggle>
    </div>
  );
}
