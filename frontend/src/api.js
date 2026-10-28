// 8010, not 8000 - avoids clashing with other local projects on the same port.
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8010";

async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`${path} -> ${res.status}`);
  }
  return res.json();
}

export function fetchDams() {
  return getJson("/api/dams");
}

export function fetchDamTimeseries(damName) {
  return getJson(`/api/dams/${encodeURIComponent(damName)}/timeseries`);
}

export function fetchGridTimeseries() {
  return getJson("/api/grid/timeseries");
}

export function fetchScenarios() {
  return getJson("/api/scenarios");
}

export function fetchScenarioDetail(scenarioName) {
  return getJson(`/api/scenarios/${encodeURIComponent(scenarioName)}`);
}

export function fetchScenarioTrajectory(scenarioName) {
  return getJson(`/api/scenarios/${encodeURIComponent(scenarioName)}/trajectory`);
}

export function fetchScenarioBalance(scenarioName) {
  return getJson(`/api/scenarios/${encodeURIComponent(scenarioName)}/balance`);
}
