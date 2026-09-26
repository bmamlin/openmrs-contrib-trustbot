"""Security-focused tests for the /revoke command's authorization checks.

Mirrors test_slack_trust_command.py. Per the slack-revoke-command spec:
signature verification happens before anything else, and a command from
outside the trusted channel is rejected silently (no rule-engine action,
no visible response).
"""

import hashlib
import hmac
import importlib
import sys
import time
from unittest.mock import MagicMock
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from src.integrations import keycloak as keycloak_integration

SIGNING_SECRET = "test-signing-secret"
TRUSTED_CHANNEL = "C0123456789"

CONFIG_YAML = """
discourse:
  base_url: "https://talk.openmrs.org"
keycloak:
  base_url: "https://id-new.openmrs.org"
  realm: "OpenMRS"
slack:
  trusted_channel_id: "{trusted_channel_id}"
rate_limiting:
  discourse_webhook:
    max_requests: 60
    window_seconds: 60
  slack_commands:
    max_requests: 10
    window_seconds: 60
database:
  path: "{db_path}"
"""


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        CONFIG_YAML.format(trusted_channel_id=TRUSTED_CHANNEL, db_path=tmp_path / "audit.db")
    )

    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "dummy-client-secret")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-dummy-token")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("DISCOURSE_API_KEY", "dummy-discourse-api-key")
    monkeypatch.setenv("DISCOURSE_API_USERNAME", "dummy-discourse-api-username")

    sys.modules.pop("src.main", None)
    main = importlib.import_module("src.main")

    with TestClient(main.app) as client:
        yield client

    sys.modules.pop("src.main", None)
    keycloak_integration._client = None


@pytest.fixture
def mock_keycloak_client():
    client = MagicMock()
    keycloak_integration.set_client(client)
    return client


def slack_command_body(*, channel_id: str, text: str = "jdoe", user_name: str = "alice") -> str:
    return urlencode(
        {
            "token": "unused-deprecated-verification-token",
            "team_id": "T0123456789",
            "channel_id": channel_id,
            "user_id": "U0123456789",
            "user_name": user_name,
            "command": "/revoke",
            "text": text,
            "response_url": "https://hooks.slack.com/commands/T0123456789/000/xxx",
            "trigger_id": "000.000.abc",
        }
    )


def sign(body: str, timestamp: str) -> str:
    basestring = f"v0:{timestamp}:{body}".encode()
    digest = hmac.new(SIGNING_SECRET.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def post_command(client: TestClient, body: str, *, signature: str, timestamp: str):
    return client.post(
        "/slack/commands",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Signature": signature,
            "X-Slack-Request-Timestamp": timestamp,
        },
    )


def test_invalid_signature_is_rejected_before_any_processing(app_client, mock_keycloak_client):
    body = slack_command_body(channel_id=TRUSTED_CHANNEL)
    timestamp = str(int(time.time()))

    response = post_command(app_client, body, signature="v0=not-a-real-signature", timestamp=timestamp)

    assert response.status_code == 401
    mock_keycloak_client.remove_user_from_groups.assert_not_called()

    conn = app_client.app.state.audit_conn
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_valid_signature_from_unauthorized_channel_is_silently_rejected(
    app_client, mock_keycloak_client
):
    body = slack_command_body(channel_id="C_SOME_OTHER_CHANNEL")
    timestamp = str(int(time.time()))
    signature = sign(body, timestamp)

    response = post_command(app_client, body, signature=signature, timestamp=timestamp)

    assert response.status_code == 200
    # No visible Slack message and no rule-engine action for the wrong channel.
    mock_keycloak_client.remove_user_from_groups.assert_not_called()

    conn = app_client.app.state.audit_conn
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
