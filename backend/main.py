"""FastAPI app serving the dam storage/rainfall/geometry data straight from
the DuckDB warehouse. No write endpoints - refreshing data is `make refresh`
(warehouse/orchestrator.py), run separately, not triggered from this API.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.db import Store

app = FastAPI(title="seq-water-scenarios API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev origin only - unused in
    allow_methods=["GET"],  # Docker, where the built frontend is served same-origin
    allow_headers=["*"],
)

store: Store | None = None


@app.on_event("startup")
def _load_store() -> None:
    global store
    store = Store()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "warehouseLoaded": store is not None}


@app.get("/api/dams")
def dams() -> dict:
    return store.dams_geojson()


@app.get("/api/dams/{dam_name}/timeseries")
def dam_timeseries(dam_name: str) -> list[dict]:
    if dam_name not in store.dam_names():
        raise HTTPException(status_code=404, detail=f"unknown dam: {dam_name}")
    return store.dam_timeseries(dam_name)


@app.get("/api/grid/timeseries")
def grid_timeseries() -> list[dict]:
    return store.grid_timeseries()


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    return store.scenario_list()


@app.get("/api/scenarios/{scenario_name}")
def scenario_detail(scenario_name: str) -> dict:
    if scenario_name not in store.scenario_names():
        raise HTTPException(status_code=404, detail=f"unknown scenario: {scenario_name}")
    return store.scenario_detail(scenario_name)


@app.get("/api/scenarios/{scenario_name}/trajectory")
def scenario_trajectory(scenario_name: str) -> dict:
    if scenario_name not in store.scenario_names():
        raise HTTPException(status_code=404, detail=f"unknown scenario: {scenario_name}")
    return store.scenario_trajectory(scenario_name)


@app.get("/api/scenarios/{scenario_name}/balance")
def scenario_balance(scenario_name: str) -> list[dict]:
    if scenario_name not in store.scenario_names():
        raise HTTPException(status_code=404, detail=f"unknown scenario: {scenario_name}")
    return store.scenario_balance(scenario_name)


# Serves the Vite build output in Docker. Absent in local dev, where Vite's
# own dev server on :5173 serves the frontend instead and CORS above covers it.
_frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if _frontend_dist.exists():
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="frontend")
