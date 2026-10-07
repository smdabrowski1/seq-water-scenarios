// Real Seqwater drought-response tiers (Water Security Program 2023, Figure
// 10 - see docs/decisions.md) - not invented thresholds. What fraction of
// the scenario's replayed rainfall sequences cross each one, and when.
const TRIGGER_LABELS = {
  pre_drought: "Pre-drought (70%)",
  drought_declared: "Drought declared (50%)",
  extreme_drought: "Extreme drought (25%)",
  emsv: "EMSV - most severe (8-10%)",
};

export default function TriggerCrossingsPanel({ triggers }) {
  if (!triggers?.length) return null;

  return (
    <div className="trigger-crossings-panel">
      <h4>Drought trigger crossings</h4>
      <table className="trigger-table">
        <thead>
          <tr>
            <th>Trigger</th>
            <th>Probability</th>
            <th>Expected</th>
          </tr>
        </thead>
        <tbody>
          {triggers.map((row) => (
            <tr key={row.trigger_name}>
              <td>{TRIGGER_LABELS[row.trigger_name] ?? row.trigger_name}</td>
              <td>{Math.round(row.crossing_probability * 100)}%</td>
              <td>
                {row.expected_crossing_date
                  ? row.expected_crossing_date.slice(0, 10)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
