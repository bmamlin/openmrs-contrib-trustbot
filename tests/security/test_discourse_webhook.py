"""Security-focused tests for the Discourse webhook endpoint's authorization checks.

Mirrors test_slack_trust_command.py, but through the real app (src.main)
rather than an isolated router, to confirm the full wiring (config +
env vars + mounted route) rejects as expected. Per the
discourse-webhook-trigger and discourse-workflow-trigger specs: signature
verification happens before anything else (403) for both delivery
mechanisms, and an unrecognized workflow name is no longer a rejection —
any name a rule references is accepted (see
test_valid_signature_with_unreferenced_workflow_name_matches_nothing).
"""

import hashlib
import hmac
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.integrations import keycloak as keycloak_integration

EXAMPLE_RULES = Path(__file__).parents[2] / "config" / "rules.example.yaml"

WEBHOOK_SECRET = "test-webhook-secret"
WORKFLOW_SECRET = "test-workflow-secret"
WORKFLOW_NAME = "trusted"

CONFIG_YAML = """
discourse:
  base_url: "https://talk.openmrs.org"
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
    config_path.write_text(CONFIG_YAML.format(db_path=tmp_path / "audit.db"))

    monkeypatch.setenv("CONFIG_PATH", str(config_path))
    monkeypatch.setenv("KEYCLOAK_CLIENT_ID", "dummy-client-id")
    monkeypatch.setenv("KEYCLOAK_CLIENT_SECRET", "dummy-client-secret")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-dummy-token")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "dummy-signing-secret")
    monkeypatch.setenv("DISCOURSE_API_KEY", "dummy-discourse-api-key")
    monkeypatch.setenv("DISCOURSE_API_USERNAME", "dummy-discourse-api-username")
    monkeypatch.setenv("DISCOURSE_WORKFLOW_SECRET", WORKFLOW_SECRET)
    monkeypatch.setenv("DISCOURSE_WEBHOOK_SECRET", WEBHOOK_SECRET)
    monkeypatch.setenv("ADMIN_API_TOKEN", "dummy-admin-token")
    monkeypatch.setenv("RULES_PATH", str(EXAMPLE_RULES))

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


def workflow_body(*, username: str = "jdoe") -> bytes:
    payload = {"username": username, "old_trust_level": 1, "new_trust_level": 2}
    return json.dumps(payload).encode()


def sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_workflow(client: TestClient, body: bytes, *, signature: str, workflow: str):
    return client.post(
        "/webhook/discourse",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Discourse-Workflow": workflow,
            "X-Discourse-Workflow-Secret": signature,
        },
    )


def post_native_webhook(client: TestClient, body: bytes, *, signature: str, event_name: str):
    return client.post(
        "/webhook/discourse",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Discourse-Event": event_name,
            "X-Discourse-Event-Signature": signature,
        },
    )


def test_workflow_invalid_signature_is_rejected_before_any_processing(app_client, mock_keycloak_client):
    body = workflow_body()

    response = post_workflow(app_client, body, signature="sha256=" + "0" * 64, workflow=WORKFLOW_NAME)

    assert response.status_code == 403
    mock_keycloak_client.add_user_to_groups.assert_not_called()

    conn = app_client.app.state.audit_conn
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_valid_signature_with_unreferenced_workflow_name_matches_nothing(app_client, mock_keycloak_client):
    # No rule in the real example rules.yaml references this name --
    # any workflow name is accepted at the signature layer (there is no
    # single hardcoded one), it just matches no rule and does nothing.
    body = workflow_body()

    response = post_workflow(app_client, body, signature=sign(body, WORKFLOW_SECRET), workflow="some-other-workflow")

    assert response.status_code == 200
    mock_keycloak_client.add_user_to_groups.assert_not_called()

    conn = app_client.app.state.audit_conn
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_native_webhook_invalid_signature_is_rejected_before_any_processing(app_client, mock_keycloak_client):
    body = json.dumps({"user": {"username": "jdoe"}}).encode()

    response = post_native_webhook(
        app_client, body, signature="sha256=" + "0" * 64, event_name="user_promoted"
    )

    assert response.status_code == 403
    mock_keycloak_client.add_user_to_groups.assert_not_called()

    conn = app_client.app.state.audit_conn
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_native_webhook_valid_signature_with_unsupported_event_name_takes_no_action(
    app_client, mock_keycloak_client
):
    body = json.dumps({"user": {"username": "jdoe"}}).encode()

    response = post_native_webhook(
        app_client, body, signature=sign(body, WEBHOOK_SECRET), event_name="some_unsupported_event"
    )

    assert response.status_code == 200
    mock_keycloak_client.add_user_to_groups.assert_not_called()

    conn = app_client.app.state.audit_conn
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_native_webhook_user_badge_granted_with_no_username_returns_400(
    app_client, mock_keycloak_client
):
    # The real payload shape Discourse sends today (confirmed via live
    # capture): no username anywhere, only a numeric user_id.
    body = json.dumps(
        {"user_badge": {"id": 1, "badge_id": 2, "user_id": 3569, "granted_by_id": -1}}
    ).encode()

    response = post_native_webhook(
        app_client, body, signature=sign(body, WEBHOOK_SECRET), event_name="user_badge_granted"
    )

    assert response.status_code == 400
    mock_keycloak_client.add_user_to_groups.assert_not_called()

    conn = app_client.app.state.audit_conn
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
