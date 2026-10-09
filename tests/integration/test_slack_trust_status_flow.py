"""End-to-end /trust-status flow: Slack command -> read/aggregate -> respond.

Unlike /trust and /trust-revoke, this never reaches the rules engine (per spec).
Exercises src.integrations.slack._handle_trust_status() directly (bypassing
slack-bolt's HTTP/signature layer, out of scope here) with mocked Keycloak
and Discourse clients and a real temp audit DB seeded via record_event().
"""

from unittest.mock import MagicMock

import pytest

from src.audit.db import get_connection, record_event
from src.integrations import discourse as discourse_integration
from src.integrations import keycloak as keycloak_integration
from src.integrations.keycloak import UserNotFoundError
from src.integrations.slack import SlackContext, _handle_trust_status

TRUSTED_CHANNEL = "C0123456789"


@pytest.fixture
def context(tmp_path):
    conn = get_connection(str(tmp_path / "audit.db"))
    yield SlackContext(trusted_channel_id=TRUSTED_CHANNEL, audit_conn=conn)
    conn.close()


@pytest.fixture(autouse=True)
def reset_clients():
    yield
    keycloak_integration._client = None
    discourse_integration._client = None


def make_command(text="jdoe", channel_id=TRUSTED_CHANNEL, user_name="alice"):
    return {"channel_id": channel_id, "text": text, "user_name": user_name}


def seed_audit_row(conn, openmrs_id="jdoe"):
    record_event(
        conn,
        openmrs_id=openmrs_id,
        trigger="slack_trust_command",
        trigger_src="alice",
        rule_name="Grant community edit access (manual /trust)",
        action="keycloak_add_groups",
        action_detail='["jira-users"]',
        status="success",
        detail=None,
    )


def test_full_success(context):
    seed_audit_row(context.audit_conn)
    row_count_before = context.audit_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]

    keycloak_client = MagicMock()
    keycloak_client.get_user_groups.return_value = ["jira-users"]
    keycloak_integration.set_client(keycloak_client)

    discourse_client = MagicMock()
    discourse_client.get_trust_level.return_value = 2
    discourse_integration.set_client(discourse_client)

    responses = []
    _handle_trust_status(make_command(), context, responses.append)

    assert len(responses) == 1
    response = responses[0]
    assert "jira-users" in response
    assert "Discourse trust level: 2" in response
    assert "keycloak_add_groups" in response

    # /trust-status must not write to the audit log itself (per design.md).
    row_count_after = context.audit_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    assert row_count_after == row_count_before


def test_discourse_unavailable_but_keycloak_and_audit_ok(context):
    seed_audit_row(context.audit_conn)

    keycloak_client = MagicMock()
    keycloak_client.get_user_groups.return_value = ["jira-users"]
    keycloak_integration.set_client(keycloak_client)

    discourse_client = MagicMock()
    discourse_client.get_trust_level.side_effect = RuntimeError("connection refused")
    discourse_integration.set_client(discourse_client)

    responses = []
    _handle_trust_status(make_command(), context, responses.append)

    response = responses[0]
    assert "jira-users" in response
    assert "Discourse trust level: unavailable" in response
    assert "keycloak_add_groups" in response


def test_keycloak_connectivity_failure_but_discourse_and_audit_ok(context):
    seed_audit_row(context.audit_conn)

    keycloak_client = MagicMock()
    keycloak_client.get_user_groups.side_effect = RuntimeError("connection refused")
    keycloak_integration.set_client(keycloak_client)

    discourse_client = MagicMock()
    discourse_client.get_trust_level.return_value = 3
    discourse_integration.set_client(discourse_client)

    responses = []
    _handle_trust_status(make_command(), context, responses.append)

    response = responses[0]
    assert "Keycloak groups: unavailable" in response
    assert "Discourse trust level: 3" in response
    assert "keycloak_add_groups" in response


def test_unknown_openmrs_id_short_circuits_before_discourse_and_audit(context):
    keycloak_client = MagicMock()
    keycloak_client.get_user_groups.side_effect = UserNotFoundError("ghost")
    keycloak_integration.set_client(keycloak_client)

    discourse_client = MagicMock()
    discourse_integration.set_client(discourse_client)

    responses = []
    _handle_trust_status(make_command(text="ghost"), context, responses.append)

    assert len(responses) == 1
    assert "not found" in responses[0]
    assert "ghost" in responses[0]
    discourse_client.get_trust_level.assert_not_called()


def test_wrong_channel_produces_no_response(context):
    keycloak_client = MagicMock()
    keycloak_integration.set_client(keycloak_client)
    discourse_client = MagicMock()
    discourse_integration.set_client(discourse_client)

    responses = []
    _handle_trust_status(make_command(channel_id="C_UNAUTHORIZED"), context, responses.append)

    assert responses == []
    keycloak_client.get_user_groups.assert_not_called()
    discourse_client.get_trust_level.assert_not_called()


def test_wrong_channel_logs_warning(context, caplog):
    keycloak_client = MagicMock()
    keycloak_integration.set_client(keycloak_client)
    discourse_client = MagicMock()
    discourse_integration.set_client(discourse_client)

    with caplog.at_level("WARNING"):
        _handle_trust_status(make_command(channel_id="C_UNAUTHORIZED"), context, lambda *_: None)

    assert any(record.levelname == "WARNING" for record in caplog.records)
