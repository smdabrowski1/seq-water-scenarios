// SPEC.md section 6.4's actual deliverable: one row per supply option, the
// year a planner would need to commit by - or, for options whose lead time
// genuinely isn't published anywhere sourced (see seed_supply_options),
// a clearly-styled "not yet published" rather than a blank cell implying
// missing data.
export default function CommitByPanel({ commitBy }) {
  if (!commitBy?.length) return null;

  const sorted = [...commitBy].sort((a, b) => {
    if (a.commit_by_year == null) return 1;
    if (b.commit_by_year == null) return -1;
    return a.commit_by_year - b.commit_by_year;
  });

  return (
    <div className="commit-by-panel">
      <h4>Commit-by dates</h4>
      <ul className="commit-by-list">
        {sorted.map((row) => (
          <li key={row.option_name} className="commit-by-row">
            <span className="commit-by-option">{row.option_name}</span>
            {row.commit_by_year != null ? (
              <span className="commit-by-year">{row.commit_by_year}</span>
            ) : (
              <span className="commit-by-unknown">
                {row.lead_time_years === "TODO-VERIFY"
                  ? "lead time not yet published"
                  : "no shortfall in this scenario"}
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
