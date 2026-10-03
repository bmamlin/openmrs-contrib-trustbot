"""End-to-end native Discourse webhook flow: webhook -> rules engine -> Keycloak -> audit log.

Exercises the real POST /webhook/discourse route (full signature
verification included, unlike the rejection-path unit tests) against a
test rules.yaml's `{type: webhook, name: "user_promoted"}` rule, with a
mocked KeycloakClient standing in for the live Keycloak Admin REST API.
"""

import hashlib
import hmac
import json
from unittest.mock import MagicMock

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.webhooks import create_webhooks_router
from src.audit.db import get_connection
from src.integrations import keycloak as keycloak_integration
from src.ratelimit import RateLimiter

WEBHOOK_SECRET = "test-webhook-secret"
WORKFLOW_SECRET = "test-workflow-secret"
DISCOURSE_BASE_URL = "https://talk.openmrs.org"

TEST_RULES = {
    "rules": [
        {
            "name": "Grant community edit access (user_promoted webhook)",
            "enabled": True,
            "triggers": [{"type": "webhook", "name": "user_promoted"}],
            "actions": [
                {
                    "type": "keycloak_add_groups",
                    "groups": ["jira-users", "jira-trunk-developer", "confluence-users"],
                }
            ],
        }
    ]
}


@pytest.fixture(autouse=True)
def rules_path_env(tmp_path, monkeypatch):
    rules_path = tmp_path / "rules.yaml"
    rules_path.write_text(yaml.safe_dump(TEST_RULES))
    monkeypatch.setenv("RULES_PATH", str(rules_path))


@pytest.fixture(autouse=True)
def reset_keycloak_client():
    yield
    keycloak_integration._client = None


def make_client(tmp_path):
    conn = get_connection(str(tmp_path / "audit.db"))
    router = create_webhooks_router(
        webhook_secret=WEBHOOK_SECRET,
        workflow_secret=WORKFLOW_SECRET,
        discourse_base_url=DISCOURSE_BASE_URL,
        audit_conn=conn,
        rate_limiter=RateLimiter(max_requests=1000, window_seconds=60),
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), conn


@pytest.fixture
def client(tmp_path):
    test_client, conn = make_client(tmp_path)
    with test_client:
        yield test_client, conn
    conn.close()


def sign(body: bytes) -> str:
    digest = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_user_promoted_event(test_client, *, username="jdoe", trust_level=2):
    payload = {"user_promoted": {"username": username, "trust_level": trust_level}}
    body = json.dumps(payload).encode()
    return test_client.post(
        "/webhook/discourse",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Discourse-Event": "user_promoted",
            "X-Discourse-Event-Signature": sign(body),
        },
    )


def test_successful_grant(client):
    test_client, conn = client
    keycloak_client = MagicMock()
    keycloak_client.add_user_to_groups.return_value = [
        "jira-users",
        "jira-trunk-developer",
        "confluence-users",
    ]
    keycloak_integration.set_client(keycloak_client)

    response = post_user_promoted_event(test_client)

    assert response.status_code == 200
    keycloak_client.add_user_to_groups.assert_called_once()

    row = conn.execute(
        "SELECT openmrs_id, trigger, trigger_src, action, status FROM audit_log"
    ).fetchone()
    assert row == ("jdoe", "webhook", DISCOURSE_BASE_URL, "keycloak_add_groups", "success")


def test_no_op_grant_when_already_trusted(client):
    test_client, conn = client
    keycloak_client = MagicMock()
    keycloak_client.add_user_to_groups.return_value = []
    keycloak_integration.set_client(keycloak_client)

    response = post_user_promoted_event(test_client)

    assert response.status_code == 200
    status = conn.execute("SELECT status FROM audit_log").fetchone()[0]
    assert status == "no_change"


def test_no_rule_matches_different_event_name(client):
    test_client, conn = client
    keycloak_client = MagicMock()
    keycloak_integration.set_client(keycloak_client)

    body = json.dumps({"user_badge": {"username": "jdoe", "badge_id": 1}}).encode()
    response = test_client.post(
        "/webhook/discourse",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Discourse-Event": "user_badge_granted",
            "X-Discourse-Event-Signature": sign(body),
        },
    )

    assert response.status_code == 200
    keycloak_client.add_user_to_groups.assert_not_called()
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
