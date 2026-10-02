"""Security-focused tests for the Discourse webhook endpoint's authorization checks.

Mirrors test_slack_trust_command.py, but through the real app (src.main)
rather than an isolated router, to confirm the full wiring (config +
env vars + mounted route) rejects as expected. Per the
discourse-trust-level-trigger spec: signature verification happens before
anything else (403), and a request with the wrong workflow name is
rejected (400) before any downstream processing.
"""

import hashlib
import hmac
import importlib
import json
import sys
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.integrations import keycloak as keycloak_integration

WEBHOOK_SECRET = "test-webhook-secret"
WORKFLOW_NAME = "trusted"

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
  trusted_channel_id: "C0123456789"
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
        CONFIG_YAML.format(workflow_name=WORKFLOW_NAME, db_path=tmp_path / "audit.db")
    )

    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "dummy-client-secret")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-dummy-token")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "dummy-signing-secret")
    monkeypatch.setenv("DISCOURSE_API_KEY", "dummy-discourse-api-key")
    monkeypatch.setenv("DISCOURSE_API_USERNAME", "dummy-discourse-api-username")
    monkeypatch.setenv("DISCOURSE_WORKFLOW_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("ADMIN_API_TOKEN", "dummy-admin-token")

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


def webhook_body(*, username: str = "jdoe") -> bytes:
    payload = {
        "username": username,
        "old_trust_level": 1,
        "new_trust_level": 2,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    return json.dumps(payload).encode()


def sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_webhook(client: TestClient, body: bytes, *, signature: str, workflow: str):
    return client.post(
        "/webhook/discourse",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Discourse-Workflow": workflow,
            "X-Discourse-Workflow-Secret": signature,
        },
    )


def test_invalid_signature_is_rejected_before_any_processing(app_client, mock_keycloak_client):
    body = webhook_body()

    response = post_webhook(app_client, body, signature="sha256=" + "0" * 64, workflow=WORKFLOW_NAME)

    assert response.status_code == 403
    mock_keycloak_client.add_user_to_groups.assert_not_called()

    conn = app_client.app.state.audit_conn
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_valid_signature_with_wrong_workflow_name_is_rejected(app_client, mock_keycloak_client):
    body = webhook_body()

    response = post_webhook(app_client, body, signature=sign(body), workflow="some-other-workflow")

    assert response.status_code == 400
    mock_keycloak_client.add_user_to_groups.assert_not_called()

    conn = app_client.app.state.audit_conn
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
