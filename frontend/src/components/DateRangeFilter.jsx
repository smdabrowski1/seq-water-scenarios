// Standard UI, not a chart mark (dataviz skill: "filters are standard UI...
// one row, above the charts"). A year dropdown rather than fixed day-count
// presets (90d/1yr/2yr/All) - this data is naturally year-shaped (so "look at
// 2023" is a meaningful, nameable question in a way "look at the last 587
// days" isn't), and it scales to however many years the warehouse ends up
// holding without needing new preset buttons added by hand. The dual-handle
// DateScrubber below can still select any custom window; this dropdown is
// just the fast path to a whole calendar year or the whole history.
export default function DateRangeFilter({ allDates, windowStart, windowEnd, onChange }) {
  if (!allDates?.length) return null;

  const years = [];
  const firstYear = Number(allDates[0].slice(0, 4));
  const lastYear = Number(allDates[allDates.length - 1].slice(0, 4));
  for (let y = lastYear; y >= firstYear; y -= 1) years.push(y);

  // "All" can't be expressed as a single year, so it's its own sentinel
  // rather than overloading one of the year values.
  const isAll = windowStart == null && windowEnd == null;
  const isWholeYear =
    !isAll &&
    windowStart?.endsWith("-01-01") &&
    windowEnd?.endsWith("-12-31") &&
    windowStart.slice(0, 4) === windowEnd.slice(0, 4);
  const value = isAll ? "all" : isWholeYear ? windowStart.slice(0, 4) : "custom";

  const handleChange = (e) => {
    const v = e.target.value;
    if (v === "all") {
      onChange(null, null);
      return;
    }
    // Clamped against the real data extent, not the calendar year's literal
    // bounds - the first/last year in the dropdown is usually partial.
    const start = `${v}-01-01` < allDates[0] ? allDates[0] : `${v}-01-01`;
    const end = `${v}-12-31` > allDates[allDates.length - 1] ? allDates[allDates.length - 1] : `${v}-12-31`;
    onChange(start, end);
  };

  return (
    <label className="year-filter">
      View
      <select value={value} onChange={handleChange}>
        <option value="all">
          All years ({firstYear}-{lastYear})
        </option>
        {years.map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
        {value === "custom" && (
          <option value="custom" disabled>
            Custom range
          </option>
        )}
      </select>
    </label>
  );
}

export function filterByWindow(rows, windowStart, windowEnd) {
  if (!rows?.length) return rows;
  const start = windowStart ?? rows[0].date;
  const end = windowEnd ?? rows[rows.length - 1].date;
  return rows.filter((r) => r.date >= start && r.date <= end);
}
