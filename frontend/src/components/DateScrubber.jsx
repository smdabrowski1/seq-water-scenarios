import { useEffect, useState } from "react";

// Two-handle slider at the bottom of the chart - drag either end to open up
// any window across the full history, not just a fixed-length window panned
// from one handle.
//
// Visual drag position is local state; it only commits to the parent (which
// triggers a full chart rebuild) on release, so dragging never fires more
// than one real redraw. A naive version re-rendered both Plot charts on
// every `input` event during the drag, which caused a "page jumps on click"
// bug - see plotUtils.js for the actual fix.
export default function DateScrubber({ allDates, windowStart, windowEnd, onChange }) {
  const maxIndex = (allDates?.length ?? 1) - 1;
  const committedStart = Math.max(0, allDates?.indexOf(windowStart) ?? 0);
  const committedEnd = windowEnd ? Math.max(0, allDates.indexOf(windowEnd)) : maxIndex;
  const [liveStart, setLiveStart] = useState(committedStart);
  const [liveEnd, setLiveEnd] = useState(committedEnd);
  // Tracks which thumb was last touched so its handle draws on top when the
  // two are close together or overlap - otherwise whichever is later in the
  // DOM always wins the hit-test and the other becomes undraggable.
  const [activeThumb, setActiveThumb] = useState("end");

  useEffect(() => setLiveStart(committedStart), [committedStart]);
  useEffect(() => setLiveEnd(committedEnd), [committedEnd]);

  if (!allDates?.length) return null;

  const commitStart = (index) => onChange(allDates[Math.min(index, liveEnd)], allDates[liveEnd]);
  const commitEnd = (index) => onChange(allDates[liveStart], allDates[Math.max(index, liveStart)]);

  const pctStart = (liveStart / maxIndex) * 100;
  const pctEnd = (liveEnd / maxIndex) * 100;

  return (
    <div className="date-scrubber">
      <div className="date-scrubber-track">
        <div className="date-scrubber-rail" />
        <div
          className="date-scrubber-highlight"
          style={{ left: `${pctStart}%`, right: `${100 - pctEnd}%` }}
        />
        <input
          type="range"
          className={`date-scrubber-thumb date-scrubber-thumb-start${activeThumb === "start" ? " is-active" : ""}`}
          min={0}
          max={maxIndex}
          value={liveStart}
          onChange={(e) => setLiveStart(Math.min(Number(e.target.value), liveEnd))}
          onMouseUp={(e) => commitStart(Number(e.target.value))}
          onTouchEnd={(e) => commitStart(Number(e.target.value))}
          onKeyUp={(e) => commitStart(Number(e.target.value))}
          onMouseDown={(e) => {
            setActiveThumb("start");
            e.currentTarget.focus({ preventScroll: true });
          }}
          onTouchStart={() => setActiveThumb("start")}
          aria-label="Window start date"
        />
        <input
          type="range"
          className={`date-scrubber-thumb date-scrubber-thumb-end${activeThumb === "end" ? " is-active" : ""}`}
          min={0}
          max={maxIndex}
          value={liveEnd}
          onChange={(e) => setLiveEnd(Math.max(Number(e.target.value), liveStart))}
          onMouseUp={(e) => commitEnd(Number(e.target.value))}
          onTouchEnd={(e) => commitEnd(Number(e.target.value))}
          onKeyUp={(e) => commitEnd(Number(e.target.value))}
          onMouseDown={(e) => {
            setActiveThumb("end");
            e.currentTarget.focus({ preventScroll: true });
          }}
          onTouchStart={() => setActiveThumb("end")}
          aria-label="Window end date"
        />
      </div>
      <div className="date-scrubber-labels">
        <span>{allDates[0]}</span>
        <span className="date-scrubber-current">
          {allDates[liveStart]} &ndash; {allDates[liveEnd]}
        </span>
        <span>{allDates[maxIndex]}</span>
      </div>
    </div>
  );
}
