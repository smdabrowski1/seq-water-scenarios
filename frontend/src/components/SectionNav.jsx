// Deliberately large, high-contrast, unambiguous buttons - not a subtle tab
// strip. Big touch targets (min ~56px tall), bold labels plus a plain-
// language subtitle so the destination is obvious before clicking, and a
// strong accent-filled active state - built to be easy to spot and click for
// any age/familiarity with dashboards, not just a compact UI convention.
const SECTIONS = [
  {
    id: "observed",
    label: "Current & History",
    subtitle: "Dam levels and rainfall, now and over time",
  },
  {
    id: "scenarios",
    label: "Scenarios",
    subtitle: "What could happen next, and when action is needed",
  },
];

export default function SectionNav({ activeSection, onSelect }) {
  return (
    <nav className="section-nav" aria-label="Dashboard section">
      {SECTIONS.map((section) => (
        <button
          key={section.id}
          type="button"
          className={
            activeSection === section.id ? "section-nav-button is-active" : "section-nav-button"
          }
          onClick={() => onSelect(section.id)}
          aria-current={activeSection === section.id ? "page" : undefined}
        >
          <span className="section-nav-label">{section.label}</span>
          <span className="section-nav-subtitle">{section.subtitle}</span>
        </button>
      ))}
    </nav>
  );
}
