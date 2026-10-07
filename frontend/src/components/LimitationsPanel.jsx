import InfoToggle from "./InfoToggle.jsx";

// A real, readable summary of scenarios/LIMITATIONS.md - that file is
// genuinely the source of truth (SPEC.md's mandatory limitations section),
// but it lives in the repo, not the deployed app, so a dashboard viewer had
// no way to actually see it before. Condensed here to what a non-technical
// viewer needs to correctly weigh these numbers, not the full engineering
// detail.
export default function LimitationsPanel() {
  return (
    <InfoToggle label="Limitations & assumptions">
      <ul className="limitations-list">
        <li>
          The storage model is fit on the whole SEQ Water Grid, not individual dams, and is
          validated only against the last ~5 years of data (2021-2026) - which never included a
          real drought. Scenarios whose rainfall falls outside that range (most of the drought
          scenarios do) are genuine extrapolation, flagged on the chart.
        </li>
        <li>
          Per-person demand is held constant for each scenario (e.g. 140 L/day throughout a
          drought) - real usage actually responds to restriction announcements and weather day
          to day.
        </li>
        <li>
          Climate adjustment scales historical rainfall by a fixed percentage - it preserves the
          real historical pattern of wet/dry spells but cannot invent a genuinely new one.
        </li>
        <li>
          Existing supply (desalination, groundwater, recycled water) is treated as a fixed
          yearly total, not a plant that could be ramped up or down during a drought.
        </li>
        <li>
          Commit-by dates are planning-relevant signals ("roughly this timeframe"), not dates a
          construction contract should be signed against without further engineering study.
        </li>
      </ul>
    </InfoToggle>
  );
}
