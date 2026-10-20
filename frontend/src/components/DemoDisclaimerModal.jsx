import { useEffect, useRef } from "react";

// Shown once, the first time the Scenarios section is opened - a real,
// personal note rather than a generic "demo" badge, since the scenario
// engine is the part of this project most likely to be mistaken for an
// operational forecasting tool if it isn't said plainly up front.
export default function DemoDisclaimerModal({ onClose }) {
  const closeButtonRef = useRef(null);

  useEffect(() => {
    closeButtonRef.current?.focus();
    const onKeyDown = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className="modal-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="demo-disclaimer-title"
        onClick={(e) => e.stopPropagation()}
      >
        <button type="button" className="modal-dismiss" onClick={onClose} aria-label="Close">
          <svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
          </svg>
        </button>

        <span className="modal-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 8v5" strokeLinecap="round" />
            <path d="M12 16.5v.01" strokeLinecap="round" />
            <circle cx="12" cy="12" r="9" />
          </svg>
        </span>

        <h3 id="demo-disclaimer-title">Before you dive in</h3>

        <p>Quick note: this Scenarios tool is a demo, not a finished planning tool.</p>
        <p>
          From experience, building something that could genuinely be used by a water
          authority for real drought and supply decisions takes significant development time
          and budget as well as input from multiple stakeholders.
        </p>
        <p>
          So please treat everything below simply as a demonstration. What I'm trying to show
          is that the app-building approach that traditionally required a team of developers
          and designers can now be accomplished by a single application builder / architect
          with the help of AI. And while code generation has become a lot more trivial,
          systems-thinking and good judgement to know which problems are worth solving are
          still of the utmost importance. I believe that with modest but real budget and the
          right
          expertise, scalable tools like this are the future of a whole-systems approach to
          planning.
        </p>

        <button ref={closeButtonRef} type="button" className="modal-close-button" onClick={onClose}>
          Got it, continue
        </button>
      </div>
    </div>
  );
}
