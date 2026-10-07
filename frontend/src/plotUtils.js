// Shared by every Observable Plot chart in this app. Swaps in a newly-built
// plot by inserting it before removing the previous one, rather than
// clearing the container first - a clear-then-rebuild leaves the container
// at zero height for a moment, which can shift surrounding content (reported
// live as a page jump when releasing the date slider). Insert-then-remove
// never has an empty gap, so the container's height never collapses.
export function swapPlot(container, prevPlotRef, newPlot) {
  if (!container) return;
  container.appendChild(newPlot);
  prevPlotRef.current?.remove();
  prevPlotRef.current = newPlot;
}
