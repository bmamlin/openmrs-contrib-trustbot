import threading

import pytest

from src.audit.db import get_connection, get_recent_events, record_event


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "audit.db"
    connection = get_connection(str(db_path))
    yield connection
    connection.close()


def test_record_event_inserts_a_row(conn):
    record_event(
        conn,
        openmrs_id="jdoe",
        trigger="slack_trust_command",
        trigger_src="alice",
        rule_name="Grant community edit access (manual /trust)",
        action="keycloak_add_groups",
        action_detail='["jira-users"]',
        status="success",
        detail=None,
    )

    rows = conn.execute("SELECT * FROM audit_log").fetchall()
    assert len(rows) == 1

    columns = [c[1] for c in conn.execute("PRAGMA table_info(audit_log)")]
    row = dict(zip(columns, rows[0]))
    assert row["openmrs_id"] == "jdoe"
    assert row["trigger"] == "slack_trust_command"
    assert row["trigger_src"] == "alice"
    assert row["status"] == "success"


def test_record_event_appends_rather_than_overwrites(conn):
    for i in range(2):
        record_event(
            conn,
            openmrs_id=f"user{i}",
            trigger="slack_trust_command",
            trigger_src="alice",
            rule_name="Grant community edit access (manual /trust)",
            action="keycloak_add_groups",
            action_detail=None,
            status="no_change",
            detail="already a member",
        )

    rows = conn.execute("SELECT openmrs_id FROM audit_log ORDER BY id").fetchall()
    assert [r[0] for r in rows] == ["user0", "user1"]


def test_record_event_works_from_a_different_thread_than_the_connection_was_opened_on(conn):
    # Regression test: the connection is opened once in the main thread
    # (src/main.py) but slack-bolt/FastAPI may dispatch a request handler
    # onto a worker thread. Before check_same_thread=False, this raised
    # sqlite3.ProgrammingError.
    errors: list[Exception] = []

    def write_from_worker_thread():
        try:
            record_event(
                conn,
                openmrs_id="jdoe",
                trigger="slack_trust_command",
                trigger_src="alice",
                rule_name="rule",
                action="keycloak_add_groups",
                action_detail=None,
                status="success",
                detail=None,
            )
        except Exception as exc:  # noqa: BLE001 - captured for the assertion below
            errors.append(exc)

    thread = threading.Thread(target=write_from_worker_thread)
    thread.start()
    thread.join()

    assert errors == []
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 1


def test_get_recent_events_returns_only_that_users_rows_newest_first(conn):
    for openmrs_id, action_detail in [
        ("jdoe", "first"),
        ("other-user", "should-not-appear"),
        ("jdoe", "second"),
        ("jdoe", "third"),
    ]:
        record_event(
            conn,
            openmrs_id=openmrs_id,
            trigger="slack_trust_command",
            trigger_src="alice",
            rule_name="rule",
            action="keycloak_add_groups",
            action_detail=action_detail,
            status="success",
            detail=None,
        )

    events = get_recent_events(conn, "jdoe", limit=2)

    assert [e["action_detail"] for e in events] == ["third", "second"]


def test_record_event_rejects_unknown_status(conn):
    with pytest.raises(ValueError):
        record_event(
            conn,
            openmrs_id="jdoe",
            trigger="slack_trust_command",
            trigger_src="alice",
            rule_name="rule",
            action="keycloak_add_groups",
            action_detail=None,
            status="pending",
            detail=None,
        )
