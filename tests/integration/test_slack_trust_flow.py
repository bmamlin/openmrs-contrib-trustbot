"""End-to-end /trust flow: Slack command -> rules engine -> Keycloak -> audit log.

Exercises src.integrations.slack._handle_trust() directly (bypassing
slack-bolt's HTTP/signature layer, which is slack-bolt's own responsibility
and out of scope here) against the real example rules.yaml, with a mocked
KeycloakClient standing in for the live Keycloak Admin REST API.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.audit.db import get_connection
from src.integrations import keycloak as keycloak_integration
from src.integrations.keycloak import UserNotFoundError
from src.integrations.slack import SlackContext, _handle_trust

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


@pytest.fixture(autouse=True)
def reset_keycloak_client():
    yield
    keycloak_integration._client = None


def make_command(text="jdoe", channel_id=TRUSTED_CHANNEL, user_name="alice"):
    return {"channel_id": channel_id, "text": text, "user_name": user_name}


def test_successful_grant(context):
    client = MagicMock()
    client.add_user_to_groups.return_value = ["jira-users", "jira-trunk-developer", "confluence-users"]
    keycloak_integration.set_client(client)

    responses = []
    _handle_trust(make_command(), context, responses.append)

    assert len(responses) == 1
    assert "granted" in responses[0]

    row = context.audit_conn.execute(
        "SELECT openmrs_id, trigger, trigger_src, action, status FROM audit_log"
    ).fetchone()
    assert row == ("jdoe", "slack_trust_command", "alice", "keycloak_add_groups", "success")


def test_no_op_grant_when_already_trusted(context):
    client = MagicMock()
    client.add_user_to_groups.return_value = []
    keycloak_integration.set_client(client)

    responses = []
    _handle_trust(make_command(), context, responses.append)

    assert "already trusted" in responses[0]

    status = context.audit_conn.execute("SELECT status FROM audit_log").fetchone()[0]
    assert status == "no_change"


def test_unknown_openmrs_id(context):
    client = MagicMock()
    client.add_user_to_groups.side_effect = UserNotFoundError("ghost")
    keycloak_integration.set_client(client)

    responses = []
    _handle_trust(make_command(text="ghost"), context, responses.append)

    assert "Could not grant access" in responses[0]
    assert "ghost" in responses[0]

    status = context.audit_conn.execute("SELECT status FROM audit_log").fetchone()[0]
    assert status == "failure"


def test_wrong_channel_produces_no_response_and_no_audit_row(context):
    client = MagicMock()
    keycloak_integration.set_client(client)

    responses = []
    _handle_trust(make_command(channel_id="C_UNAUTHORIZED"), context, responses.append)

    assert responses == []
    client.add_user_to_groups.assert_not_called()
    assert context.audit_conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_wrong_channel_logs_warning(context, caplog):
    client = MagicMock()
    keycloak_integration.set_client(client)

    with caplog.at_level("WARNING"):
        _handle_trust(make_command(channel_id="C_UNAUTHORIZED"), context, lambda *_: None)

    assert any(record.levelname == "WARNING" for record in caplog.records)
