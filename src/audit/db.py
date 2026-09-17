"""SQLite connection management and audit_log write logic.

Connects to the database at database.path (config.yaml, default
/data/audit.db), applying schema.sql if the audit_log table does not yet
exist. Writes are append-only (INSERT only — see openspec/specs/overview.md
§5.5); the service never UPDATEs or DELETEs audit rows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open (and if needed, initialize via schema.sql) the audit database."""
    raise NotImplementedError


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
    """Insert one append-only audit_log row. status must be 'success' | 'no_change' | 'failure'."""
    raise NotImplementedError
