"""Phase 0 recon: hit the SILO point API once and save the raw response.

Run manually: `uv run python -m ingest.recon_silo` (requires SILO_API_KEY in .env -
free registration at longpaddock.qld.gov.au/silo/, the registered email is the key).

Throwaway-but-committed, same rationale as ingest/recon_bom.py: inspect the real
response shape/units/date format before ingest/silo.py's parsing is trusted. Update
docs/decisions.md with what you observe.
"""

from __future__ import annotations

import json
from pathlib import Path

from dotenv import load_dotenv

from ingest.cache import Cache
from ingest.silo import fetch_point_data

SAMPLES_DIR = Path("docs/samples")


def main() -> None:
    load_dotenv()
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    cache = Cache(Path("data/.cache/recon.db"))
    try:
        # TODO-VERIFY: a real SILO station number for a SEQ catchment location.
        station_config = {"station_no": "TODO-VERIFY", "variables": ["daily_rain"]}
        df = fetch_point_data(station_config, cache)
        (SAMPLES_DIR / "silo_response.json").write_text(
            json.dumps(df.to_dicts(), indent=2, default=str)
        )
        print(f"SILO point data: {df.height} rows -> saved to docs/samples/silo_response.json")
    finally:
        cache.close()


if __name__ == "__main__":
    main()
