"""End-to-end /revoke flow: Slack command -> rules engine -> Keycloak -> audit log.

Mirrors test_slack_trust_flow.py. Exercises
src.integrations.slack._handle_revoke() directly (bypassing slack-bolt's
HTTP/signature layer, out of scope here) against the real example
rules.yaml, with a mocked KeycloakClient standing in for the live Keycloak
Admin REST API.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.audit.db import get_connection
from src.integrations import keycloak as keycloak_integration
from src.integrations.keycloak import UserNotFoundError
from src.integrations.slack import SlackContext, _handle_revoke

EXAMPLE_RULES = Path(__file__).parents[2] / "config" / "rules.example.yaml"
TRUSTED_CHANNEL = "C0123456789"


@pytest.fixture(autouse=True)
def rules_path_env(monkeypatch):
    monkeypatch.setenv("RULES_PATH", str(EXAMPLE_RULES))


@pytest.fixture
def context(tmp_path):
    conn = get_connection(str(tmp_path / "audit.db"))
    yield SlackContext(trusted_channel_id=TRUSTED_CHANNEL, audit_conn=conn)
    conn.close()


@pytest.fixture
def dry_run_context(tmp_path):
    conn = get_connection(str(tmp_path / "audit.db"))
    yield SlackContext(trusted_channel_id=TRUSTED_CHANNEL, audit_conn=conn, dry_run=True)
    conn.close()


@pytest.fixture(autouse=True)
def reset_keycloak_client():
    yield
    keycloak_integration._client = None


def make_command(text="jdoe", channel_id=TRUSTED_CHANNEL, user_name="alice"):
    return {"channel_id": channel_id, "text": text, "user_name": user_name}


def test_successful_revoke(context):
    client = MagicMock()
    client.remove_user_from_groups.return_value = ["jira-users", "jira-trunk-developer", "confluence-users"]
    keycloak_integration.set_client(client)

    responses = []
    _handle_revoke(make_command(), context, responses.append)

    assert len(responses) == 1
    assert "revoked" in responses[0]

    row = context.audit_conn.execute(
        "SELECT openmrs_id, trigger, trigger_src, action, status FROM audit_log"
    ).fetchone()
    assert row == ("jdoe", "slack_revoke_command", "alice", "keycloak_remove_groups", "success")


def test_no_op_revoke_when_already_not_trusted(context):
    client = MagicMock()
    client.remove_user_from_groups.return_value = []
    keycloak_integration.set_client(client)

    responses = []
    _handle_revoke(make_command(), context, responses.append)

    assert "already not trusted" in responses[0]

    status = context.audit_conn.execute("SELECT status FROM audit_log").fetchone()[0]
    assert status == "no_change"


def test_unknown_openmrs_id(context):
    client = MagicMock()
    client.remove_user_from_groups.side_effect = UserNotFoundError("ghost")
    keycloak_integration.set_client(client)

    responses = []
    _handle_revoke(make_command(text="ghost"), context, responses.append)

    assert "Could not revoke access" in responses[0]
    assert "ghost" in responses[0]

    status = context.audit_conn.execute("SELECT status FROM audit_log").fetchone()[0]
    assert status == "failure"


def test_wrong_channel_produces_no_response_and_no_audit_row(context):
    client = MagicMock()
    keycloak_integration.set_client(client)

    responses = []
    _handle_revoke(make_command(channel_id="C_UNAUTHORIZED"), context, responses.append)

    assert responses == []
    client.remove_user_from_groups.assert_not_called()
    assert context.audit_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_dry_run_simulates_revoke_without_mutating_keycloak(dry_run_context):
    client = MagicMock()
    client.remove_user_from_groups.return_value = [
        "jira-users",
        "jira-trunk-developer",
        "confluence-users",
    ]
    keycloak_integration.set_client(client)

    responses = []
    _handle_revoke(make_command(), dry_run_context, responses.append)

    assert len(responses) == 1
    assert "DRY RUN" in responses[0]
    assert "No change was made" in responses[0]

    row = dry_run_context.audit_conn.execute("SELECT status FROM audit_log").fetchone()
    assert row == ("dry_run",)
    client.remove_user_from_groups.assert_called_once_with(
        "jdoe", ["jira-users", "jira-trunk-developer", "confluence-users"], dry_run=True
    )


def test_wrong_channel_logs_warning(context, caplog):
    client = MagicMock()
    keycloak_integration.set_client(client)

    with caplog.at_level("WARNING"):
        _handle_revoke(make_command(channel_id="C_UNAUTHORIZED"), context, lambda *_: None)

    assert any(record.levelname == "WARNING" for record in caplog.records)
