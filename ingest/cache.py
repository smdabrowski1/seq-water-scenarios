"""Persistent on-disk HTTP cache with hand-rolled retry/backoff.

No retry library dependency (tenacity etc.) - confirmed with the user to hand-roll
this instead, since the spec asks to flag any dependency not named in its stack list
before adding it. Backed by SQLite rather than a second ad-hoc cache mechanism,
since `warehouse/registry.py` already brings in sqlite3 as a dependency.

This is what makes `make ingest` idempotent on a cold-then-warm re-run (spec's
Phase 1 done-when criterion): a cache hit within `ttl` returns immediately without
another network call.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

import httpx

_SCHEMA = """
CREATE TABLE IF NOT EXISTS http_cache (
    cache_key   TEXT PRIMARY KEY,
    url         TEXT NOT NULL,
    fetched_at  REAL NOT NULL,
    status_code INTEGER NOT NULL,
    body        TEXT NOT NULL
)
"""

DEFAULT_TTL_SECONDS = 6 * 3600  # a few hours - source data updates at most daily
MAX_RETRIES = 4
BACKOFF_BASE_SECONDS = 1.0


def _cache_key(url: str, params: dict[str, Any] | None) -> str:
    normalized = json.dumps({"url": url, "params": params or {}}, sort_keys=True)
    return hashlib.sha256(normalized.encode()).hexdigest()


class Cache:
    def __init__(self, cache_db_path: Path, client: httpx.Client | None = None) -> None:
        cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(cache_db_path)
        self._con.execute(_SCHEMA)
        self._con.commit()
        self._client = client or httpx.Client(timeout=30.0, follow_redirects=True)

    def close(self) -> None:
        self._client.close()
        self._con.close()

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        ttl: float = DEFAULT_TTL_SECONDS,
    ) -> Any:
        """Return parsed JSON for `url`, serving from cache within `ttl` seconds.

        Callers must not assume a dict - BOM KiWIS returns a top-level list for
        every request kind used in this project (see ingest/bom_kiwis.py).
        """
        return json.loads(self.get_text(url, params=params, ttl=ttl))

    def get_text(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        ttl: float = DEFAULT_TTL_SECONDS,
    ) -> str:
        """Return raw response body for `url`, serving from cache within `ttl`
        seconds - for HTML sources (ingest/seqwater_scrape.py) where the
        response isn't JSON."""
        key = _cache_key(url, params)
        row = self._con.execute(
            "SELECT fetched_at, body FROM http_cache WHERE cache_key = ?", (key,)
        ).fetchone()
        if row is not None:
            fetched_at, body = row
            if time.time() - fetched_at < ttl:
                return body

        response = self._fetch_with_retry(url, params)
        body_text = response.text
        self._con.execute(
            """
            INSERT INTO http_cache (cache_key, url, fetched_at, status_code, body)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                fetched_at = excluded.fetched_at,
                status_code = excluded.status_code,
                body = excluded.body
            """,
            (key, url, time.time(), response.status_code, body_text),
        )
        self._con.commit()
        return body_text

    def _fetch_with_retry(self, url: str, params: dict[str, Any] | None) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.get(url, params=params)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"server error {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if attempt < MAX_RETRIES - 1:
                    time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))
        assert last_exc is not None
        raise last_exc
