"""SQLite connection management and audit_log write logic.

Connects to the database at database.path (config.yaml, default
/data/audit.db), applying schema.sql if the audit_log table does not yet
exist. Writes are append-only (INSERT only — see openspec/specs/overview.md
§5.5); the service never UPDATEs or DELETEs audit rows.

The connection returned by get_connection() is created once at startup
(src/main.py) and then shared across every request. slack-bolt (and
FastAPI, for async routes) may run request handlers on a worker thread
different from the one that opened the connection, so it's opened with
check_same_thread=False; a busy_timeout is set so that if two requests do
write at the same moment, the second one waits briefly for SQLite's file
lock rather than raising "database is locked".
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open (and if needed, initialize via schema.sql) the audit database.

    Safe to share across threads (see module docstring).
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 5000")
    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())
    conn.commit()
    return conn


def record_event(
    conn: sqlite3.Connection,
    *,
    openmrs_id: str,
    trigger: str,
    trigger_src: str | None,
    rule_name: str,
    action: str,
    action_detail: str | None,
    status: str,
    detail: str | None,
) -> None:
    """Insert one append-only audit_log row. status must be 'success' | 'no_change' | 'failure' | 'dry_run'."""
    if status not in ("success", "no_change", "failure", "dry_run"):
        raise ValueError(f"invalid audit status: {status!r}")
    conn.execute(
        """
        INSERT INTO audit_log (
            timestamp, openmrs_id, trigger, trigger_src, rule_name,
            action, action_detail, status, detail
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now(UTC).isoformat(),
            openmrs_id,
            trigger,
            trigger_src,
            rule_name,
            action,
            action_detail,
            status,
            detail,
        ),
    )
    conn.commit()


def get_recent_events(conn: sqlite3.Connection, openmrs_id: str, *, limit: int = 5) -> list[dict]:
    """Return openmrs_id's most recent audit_log rows, newest first.

    Read-only; does not affect the append-only write path above.
    """
    cursor = conn.execute(
        """
        SELECT timestamp, trigger, trigger_src, rule_name, action, action_detail, status, detail
        FROM audit_log
        WHERE openmrs_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (openmrs_id, limit),
    )
    columns = [description[0] for description in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]
