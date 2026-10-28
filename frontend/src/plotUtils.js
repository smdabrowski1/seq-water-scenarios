// Shared by every Observable Plot chart in this app. Inserts the new plot
// before removing the old one - clearing the container first leaves it at
// zero height for a moment, which shifted surrounding content (showed up as
// a page jump when releasing the date slider). Insert-then-remove never
// leaves a gap.
export function swapPlot(container, prevPlotRef, newPlot) {
  if (!container) return;
  container.appendChild(newPlot);
  prevPlotRef.current?.remove();
  prevPlotRef.current = newPlot;
}
