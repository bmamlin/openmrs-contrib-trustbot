"""Security-focused tests for dry-run mode on both trigger entry points.

Through the real app (src.main, mirroring the other tests/security
fixtures' pattern, with `dry_run: true` in config.yaml): a validly-signed
Discourse webhook request and a validly-authorized /trust command each
produce a `dry_run` audit row and never call the mocked Keycloak client's
mutating methods, per the dry-run-mode spec.
"""

import hashlib
import hmac
import importlib
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from src.integrations import keycloak as keycloak_integration


class _FakeAuthTestResult:
    """Stands in for the SlackResponse slack-bolt's SingleTeamAuthorization
    middleware expects from a real `auth.test` API call, so slash-command
    requests reach our own middleware/listeners without a live Slack API call."""

    def __init__(self, data: dict):
        self._data = data
        self.headers: dict = {}

    def get(self, key, default=None):
        return self._data.get(key, default)


WORKFLOW_SECRET = "test-workflow-secret"
WEBHOOK_SECRET = "test-webhook-secret"
WORKFLOW_NAME = "trusted"
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
dry_run: true
"""


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        CONFIG_YAML.format(
            trusted_channel_id=TRUSTED_CHANNEL,
            db_path=tmp_path / "audit.db",
        )
    )

    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "dummy-client-secret")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-dummy-token")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("DISCOURSE_API_KEY", "dummy-discourse-api-key")
    monkeypatch.setenv("DISCOURSE_API_USERNAME", "dummy-discourse-api-username")
    monkeypatch.setenv("DISCOURSE_WORKFLOW_SECRET", WORKFLOW_SECRET)
    monkeypatch.setenv("DISCOURSE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("ADMIN_API_TOKEN", "dummy-admin-token")
    monkeypatch.setenv("RULES_PATH", str(Path(__file__).parents[2] / "config" / "rules.example.yaml"))

    sys.modules.pop("src.main", None)
    main = importlib.import_module("src.main")

    fake_auth_test_result = _FakeAuthTestResult(
        {"ok": True, "user_id": "U0BOTUSER", "team_id": "T0123456789", "bot_id": "B0123456789"}
    )
    with patch("slack_sdk.web.client.WebClient.auth_test", return_value=fake_auth_test_result):
        with TestClient(main.app) as client:
            yield client

    sys.modules.pop("src.main", None)
    keycloak_integration._client = None


@pytest.fixture
def mock_keycloak_client():
    client = MagicMock()
    client.add_user_to_groups.return_value = ["jira-users", "jira-trunk-developer", "confluence-users"]
    keycloak_integration.set_client(client)
    return client


def workflow_body(*, username: str = "jdoe") -> bytes:
    payload = {"username": username, "old_trust_level": 1, "new_trust_level": 2}
    return json.dumps(payload).encode()


def sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_workflow(client: TestClient, body: bytes):
    return client.post(
        "/webhook/discourse",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Discourse-Workflow": WORKFLOW_NAME,
            "X-Discourse-Workflow-Signature": sign(body, WORKFLOW_SECRET),
        },
    )


def slack_command_body(*, user_id: str = "U0123456789", user_name: str = "alice") -> str:
    return urlencode(
        {
            "token": "unused-deprecated-verification-token",
            "team_id": "T0123456789",
            "channel_id": TRUSTED_CHANNEL,
            "user_id": user_id,
            "user_name": user_name,
            "command": "/trust",
            "text": "jdoe",
            "response_url": "https://hooks.slack.com/commands/T0123456789/000/xxx",
            "trigger_id": "000.000.abc",
        }
    )


def sign_slack(body: str, timestamp: str) -> str:
    basestring = f"v0:{timestamp}:{body}".encode()
    digest = hmac.new(SIGNING_SECRET.encode(), basestring, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def wait_for_audit_row(conn, *, timeout: float = 2.0):
    """Poll for an audit_log row.

    slack-bolt dispatches command listeners on a background thread by
    default (process_before_response=False): the HTTP response returns as
    soon as ack() is called, racing with the rest of _handle_trust()
    (including the audit write) which keeps running in that thread.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = conn.execute("SELECT status FROM audit_log").fetchone()
        if row is not None:
            return row[0]
        time.sleep(0.01)
    return None


def post_command(client: TestClient, body: str):
    timestamp = str(int(time.time()))
    return client.post(
        "/slack/commands",
        content=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Signature": sign_slack(body, timestamp),
            "X-Slack-Request-Timestamp": timestamp,
        },
    )


def test_discourse_workflow_dry_run_records_dry_run_audit_row_without_mutating(
    app_client, mock_keycloak_client
):
    response = post_workflow(app_client, workflow_body())

    assert response.status_code == 200
    # dry_run=True is what actually suppresses the mutating Keycloak calls
    # (group_user_add/group_user_remove), verified at the KeycloakClient
    # level in tests/unit/integrations/test_keycloak.py -- this mock stands
    # in for the whole client, so the useful assertion here is that the
    # flag reached it, not that the (mocked) method was skipped entirely.
    mock_keycloak_client.add_user_to_groups.assert_called_once_with(
        "jdoe", ["jira-users", "jira-trunk-developer", "confluence-users"], dry_run=True
    )

    conn = app_client.app.state.audit_conn
    status = conn.execute("SELECT status FROM audit_log").fetchone()[0]
    assert status == "dry_run"


def test_slack_trust_command_dry_run_records_dry_run_audit_row_without_mutating(
    app_client, mock_keycloak_client
):
    body = slack_command_body()

    response = post_command(app_client, body)

    assert response.status_code == 200

    conn = app_client.app.state.audit_conn
    status = wait_for_audit_row(conn)
    assert status == "dry_run"
    mock_keycloak_client.add_user_to_groups.assert_called_once_with(
        "jdoe", ["jira-users", "jira-trunk-developer", "confluence-users"], dry_run=True
    )
