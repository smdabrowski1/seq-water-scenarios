import { Component } from "react";

// Without this, an uncaught error inside a chart's render effect (e.g. a
// Plot.barY/utc-scale mismatch) unmounts the entire React tree, not just
// the chart. Charts are the most likely place for a data-shape surprise, so
// they get their own boundary.
export default class ChartErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Chart failed to render:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="chart-error">
          Couldn&apos;t render this chart: {String(this.state.error.message ?? this.state.error)}
        </div>
      );
    }
    return this.props.children;
  }
}
