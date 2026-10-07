from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from warehouse import registry


@pytest.fixture
def con(tmp_path):
    db_path = tmp_path / "registry.db"
    connection = registry.connect(str(db_path))
    yield connection
    connection.close()


def test_start_run_creates_non_terminal_row(con: sqlite3.Connection):
    run_id = "test-run-1"
    registry.start_run(con, run_id)

    assert registry.has_running_job(con) is True
    row = con.execute(
        "SELECT status, is_current FROM pipeline_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    assert row == ("ingesting", 0)


def test_activate_run_flips_current_atomically(con: sqlite3.Connection):
    first_run, second_run = "run-1", "run-2"
    registry.start_run(con, first_run)
    registry.activate_run(con, first_run, warehouse_path="/tmp/first.duckdb")

    registry.start_run(con, second_run)
    registry.activate_run(con, second_run, warehouse_path="/tmp/second.duckdb")

    current = registry.get_current(con)
    assert current["run_id"] == second_run
    assert current["status"] == "active"

    first_status = con.execute(
        "SELECT status, is_current FROM pipeline_runs WHERE run_id = ?", (first_run,)
    ).fetchone()
    assert first_status == ("superseded", 0)

    # never zero or two current rows
    current_count = con.execute(
        "SELECT COUNT(*) FROM pipeline_runs WHERE is_current = 1"
    ).fetchone()[0]
    assert current_count == 1


def test_has_running_job_false_when_no_active_runs(con: sqlite3.Connection):
    assert registry.has_running_job(con) is False

    registry.start_run(con, "run-1")
    registry.activate_run(con, "run-1", warehouse_path="/tmp/a.duckdb")

    assert registry.has_running_job(con) is False


def test_reap_stale_jobs_fails_old_non_terminal_runs(con: sqlite3.Connection):
    stale_run = "stale-run"
    registry.start_run(con, stale_run)
    old_timestamp = (datetime.now(UTC) - timedelta(minutes=999)).isoformat()
    con.execute(
        "UPDATE pipeline_runs SET created_at = ? WHERE run_id = ?", (old_timestamp, stale_run)
    )
    con.commit()

    registry.reap_stale_jobs(con, stale_after_minutes=120)

    row = con.execute("SELECT status FROM pipeline_runs WHERE run_id = ?", (stale_run,)).fetchone()
    assert row[0] == "failed"
    assert registry.has_running_job(con) is False


def test_reap_stale_jobs_leaves_recent_non_terminal_runs(con: sqlite3.Connection):
    recent_run = "recent-run"
    registry.start_run(con, recent_run)

    registry.reap_stale_jobs(con, stale_after_minutes=120)

    assert registry.has_running_job(con) is True


def test_set_status_records_error_and_completed_at(con: sqlite3.Connection):
    run_id = "failing-run"
    registry.start_run(con, run_id)
    registry.set_status(con, run_id, "failed", error="boom")

    row = con.execute(
        "SELECT status, error, completed_at FROM pipeline_runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    assert row[0] == "failed"
    assert row[1] == "boom"
    assert row[2] is not None


def test_append_log_trims_to_max_lines(con: sqlite3.Connection):
    run_id = "logged-run"
    registry.start_run(con, run_id)
    for i in range(5):
        registry.append_log(con, run_id, f"line {i}", max_lines=3)

    row = con.execute("SELECT log FROM pipeline_runs WHERE run_id = ?", (run_id,)).fetchone()
    lines = row[0].splitlines()
    assert len(lines) == 3
    assert lines[-1].endswith("line 4")
