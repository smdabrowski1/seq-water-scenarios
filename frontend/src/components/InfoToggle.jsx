import { useState } from "react";

// A small, clearly-labelled toggle for explanatory text that doesn't need
// to be read upfront - chart captions, methodology notes, scenario
// descriptions. Collapsed by default so the page reads cleanly; the toggle
// itself is styled to look obviously clickable (pill button, icon, border),
// not a plain text link easy to miss.
export default function InfoToggle({ label = "What does this mean?", children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div className="info-toggle">
      <button
        type="button"
        className="info-toggle-button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span className="info-toggle-icon" aria-hidden="true">
          i
        </span>
        {open ? "Hide" : label}
        <span className="info-toggle-chevron" aria-hidden="true">
          {open ? "−" : "+"}
        </span>
      </button>
      {open && <div className="info-toggle-content">{children}</div>}
    </div>
  );
}
