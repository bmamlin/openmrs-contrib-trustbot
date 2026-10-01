"""Security-focused tests for rate limiting on both HTTP-reachable endpoints.

Through the real app (src.main, mirroring the other tests/security fixtures'
pattern): a burst of otherwise-valid requests beyond the configured limit
gets rejected for the excess ones only, per the discourse-webhook-rate-limiting
and slack-command-rate-limiting specs.
"""

import hashlib
import hmac
import importlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient

from src.integrations import keycloak as keycloak_integration
from src.integrations.slack import RATE_LIMITED_MESSAGE


class _FakeAuthTestResult:
    """Stands in for the SlackResponse slack-bolt's SingleTeamAuthorization
    middleware expects from a real `auth.test` API call, so slash-command
    requests reach our own middleware/listeners without a live Slack API call."""

    def __init__(self, data: dict):
        self._data = data
        self.headers: dict = {}

    def get(self, key, default=None):
        return self._data.get(key, default)

WEBHOOK_SECRET = "test-webhook-secret"
WORKFLOW_NAME = "trusted"
SIGNING_SECRET = "test-signing-secret"
TRUSTED_CHANNEL = "C0123456789"

CONFIG_YAML = """
discourse:
  base_url: "https://talk.openmrs.org"
  webhook:
    replay_window_seconds: 300
    workflow_name: "{workflow_name}"
keycloak:
  base_url: "https://id-new.openmrs.org"
  realm: "OpenMRS"
slack:
  trusted_channel_id: "{trusted_channel_id}"
rate_limiting:
  discourse_webhook:
    max_requests: 2
    window_seconds: 60
  slack_commands:
    max_requests: 2
    window_seconds: 60
database:
  path: "{db_path}"
"""


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        CONFIG_YAML.format(
            workflow_name=WORKFLOW_NAME,
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
    monkeypatch.setenv("DISCOURSE_WORKFLOW_SECRET", WEBHOOK_SECRET)
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


def webhook_body(*, username: str = "jdoe") -> bytes:
    payload = {
        "username": username,
        "old_trust_level": 1,
        "new_trust_level": 2,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return json.dumps(payload).encode()


def sign_webhook(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_webhook(client: TestClient, body: bytes, *, source_ip: str):
    return client.post(
        "/webhook/discourse",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Discourse-Workflow": WORKFLOW_NAME,
            "X-Discourse-Workflow-Secret": sign_webhook(body),
            "X-Forwarded-For": source_ip,
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


def test_discourse_webhook_burst_past_limit_gets_429_for_excess(app_client, mock_keycloak_client):
    source_ip = "203.0.113.42"

    responses = [post_webhook(app_client, webhook_body(), source_ip=source_ip) for _ in range(3)]

    assert [r.status_code for r in responses[:2]] == [200, 200]
    assert responses[2].status_code == 429


def test_slack_command_burst_past_limit_gets_rate_limited_message_for_excess(
    app_client, mock_keycloak_client
):
    responses = [post_command(app_client, slack_command_body()) for _ in range(3)]

    assert all(r.status_code == 200 for r in responses)
    assert RATE_LIMITED_MESSAGE not in responses[0].text
    assert RATE_LIMITED_MESSAGE not in responses[1].text
    assert RATE_LIMITED_MESSAGE in responses[2].text
