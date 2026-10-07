# Multi-stage: build the frontend, then serve it from FastAPI on one port -
# mirrors the Hobby CDM Project's Docker pattern, on a different host port
# (8010, not 8000) so both projects can run at once on the same machine.

FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
# Empty base -> relative /api/... paths, since the built frontend is served
# same-origin by this same container (unlike local dev, where Vite's dev
# server on :5173 and the backend on :8010 are different origins, needing CORS).
ENV VITE_API_BASE=""
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache "fastapi>=0.115" "uvicorn[standard]>=0.32" "duckdb>=1.0"

COPY backend/ ./backend/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV WAREHOUSE_PATH=/app/data/warehouse.duckdb

EXPOSE 8000
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
