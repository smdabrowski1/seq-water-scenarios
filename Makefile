.PHONY: refresh ingest test build serve lint

ingest:
	uv run python -m ingest.run_all

refresh:
	uv run python -m warehouse.orchestrator

test:
	uv run pytest

build:
	uv run dbt build --project-dir dbt --profiles-dir dbt

serve:
	cd frontend && npm run dev

lint:
	uv run ruff check .
	uv run ruff format --check .
