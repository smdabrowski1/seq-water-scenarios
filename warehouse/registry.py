"""SQLite-backed registry of pipeline runs.

One warehouse file per run, so one row per *run*. Answers two questions
safely across process restarts and concurrent invocations: "is a run
currently in flight" and "which run's warehouse file should the dashboard
export step read from" — the latter only ever changes inside
`activate_run`'s single transaction.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

TERMINAL_STATUSES = {"active", "superseded", "failed"}
STALE_AFTER_MINUTES = 120  # ingest + dbt build + dbt test is slower than a single fetch

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id         TEXT PRIMARY KEY,
    status         TEXT NOT NULL,
    is_current     INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL,
    completed_at   TEXT,
    error          TEXT,
    warehouse_path TEXT,
    export_path    TEXT,
    row_counts     TEXT,
    log            TEXT
)
"""


def connect(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.execute(_SCHEMA)
    con.commit()
    return con


def _now() -> str:
    return datetime.now(UTC).isoformat()


def new_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


def reap_stale_jobs(
    con: sqlite3.Connection, stale_after_minutes: int = STALE_AFTER_MINUTES
) -> None:
    """Fail any non-terminal run older than the threshold.

    A young non-terminal row can't be distinguished from a genuinely still-
    running job without a time threshold. A container crash mid-run leaves
    that run locked out for up to `stale_after_minutes` before a retry.
    """
    cutoff = (datetime.now(UTC) - timedelta(minutes=stale_after_minutes)).isoformat()
    placeholders = ",".join("?" for _ in TERMINAL_STATUSES)
    with con:
        con.execute(
            f"""
            UPDATE pipeline_runs
            SET status = 'failed', error = 'reaped: stale non-terminal run', completed_at = ?
            WHERE status NOT IN ({placeholders}) AND created_at < ?
            """,
            (_now(), *TERMINAL_STATUSES, cutoff),
        )


def has_running_job(con: sqlite3.Connection) -> bool:
    placeholders = ",".join("?" for _ in TERMINAL_STATUSES)
    row = con.execute(
        f"SELECT 1 FROM pipeline_runs WHERE status NOT IN ({placeholders}) LIMIT 1",
        tuple(TERMINAL_STATUSES),
    ).fetchone()
    return row is not None


def start_run(con: sqlite3.Connection, run_id: str) -> None:
    with con:
        con.execute(
            """
            INSERT INTO pipeline_runs (run_id, status, is_current, created_at)
            VALUES (?, 'ingesting', 0, ?)
            """,
            (run_id, _now()),
        )


def set_status(con: sqlite3.Connection, run_id: str, status: str, error: str | None = None) -> None:
    completed_at = _now() if status in TERMINAL_STATUSES else None
    with con:
        con.execute(
            """
            UPDATE pipeline_runs
            SET status = ?, error = ?, completed_at = COALESCE(?, completed_at)
            WHERE run_id = ?
            """,
            (status, error, completed_at, run_id),
        )


def append_log(con: sqlite3.Connection, run_id: str, message: str, max_lines: int = 200) -> None:
    # Not wrapped in the same transaction discipline as status/activation — a torn
    # write here is harmless, unlike a torn write to `is_current`.
    row = con.execute("SELECT log FROM pipeline_runs WHERE run_id = ?", (run_id,)).fetchone()
    existing = row[0].splitlines() if row and row[0] else []
    lines = (existing + [f"{_now()} {message}"])[-max_lines:]
    con.execute("UPDATE pipeline_runs SET log = ? WHERE run_id = ?", ("\n".join(lines), run_id))
    con.commit()


def activate_run(
    con: sqlite3.Connection,
    run_id: str,
    warehouse_path: str,
    export_path: str | None = None,
    row_counts: dict[str, int] | None = None,
) -> None:
    """Atomically flip which run is current.

    Only place in the module that changes what the dashboard export step reads
    from: old current -> superseded, new run -> is_current=1, status='active',
    in one transaction so there's never a moment with zero or two current rows.
    """
    with con:
        con.execute(
            "UPDATE pipeline_runs SET is_current = 0, status = 'superseded' WHERE is_current = 1"
        )
        con.execute(
            """
            UPDATE pipeline_runs
            SET is_current = 1, status = 'active', completed_at = ?,
                warehouse_path = ?, export_path = ?, row_counts = ?
            WHERE run_id = ?
            """,
            (
                _now(),
                warehouse_path,
                export_path,
                json.dumps(row_counts) if row_counts else None,
                run_id,
            ),
        )


def get_current(con: sqlite3.Connection) -> sqlite3.Row | None:
    cur = con.cursor()
    cur.row_factory = sqlite3.Row
    return cur.execute("SELECT * FROM pipeline_runs WHERE is_current = 1").fetchone()


def list_runs(con: sqlite3.Connection) -> Iterable[sqlite3.Row]:
    cur = con.cursor()
    cur.row_factory = sqlite3.Row
    return cur.execute("SELECT * FROM pipeline_runs ORDER BY created_at DESC").fetchall()
