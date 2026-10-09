"""End-to-end Discourse Workflow flow: workflow -> rules engine -> Keycloak -> audit log.

Exercises the real POST /webhook/discourse route (full signature
verification included, unlike the rejection-path unit tests) against the
real example rules.yaml's `{type: workflow, name: "trusted"}` rule, with
a mocked KeycloakClient standing in for the live Keycloak Admin REST API.
"""

import hashlib
import hmac
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.webhooks import create_webhooks_router
from src.audit.db import get_connection
from src.integrations import keycloak as keycloak_integration
from src.ratelimit import RateLimiter

EXAMPLE_RULES = Path(__file__).parents[2] / "config" / "rules.example.yaml"
WEBHOOK_SECRET = "test-webhook-secret"
WORKFLOW_SECRET = "test-workflow-secret"
WORKFLOW_NAME = "trusted"
DISCOURSE_BASE_URL = "https://talk.openmrs.org"


@pytest.fixture(autouse=True)
def rules_path_env(monkeypatch):
    monkeypatch.setenv("RULES_PATH", str(EXAMPLE_RULES))


@pytest.fixture(autouse=True)
def reset_keycloak_client():
    yield
    keycloak_integration._client = None


def make_client(tmp_path, *, dry_run: bool = False):
    conn = get_connection(str(tmp_path / "audit.db"))
    router = create_webhooks_router(
        webhook_secret=WEBHOOK_SECRET,
        workflow_secret=WORKFLOW_SECRET,
        discourse_base_url=DISCOURSE_BASE_URL,
        audit_conn=conn,
        rate_limiter=RateLimiter(max_requests=1000, window_seconds=60),
        dry_run=dry_run,
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
    digest = hmac.new(WORKFLOW_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def post_workflow_event(test_client, *, username="jdoe", workflow_name=WORKFLOW_NAME, **extra_payload):
    payload = {"username": username, **extra_payload}
    body = json.dumps(payload).encode()
    return test_client.post(
        "/webhook/discourse",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Discourse-Workflow": workflow_name,
            "X-Discourse-Workflow-Signature": sign(body),
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

    response = post_workflow_event(test_client, old_trust_level=1, new_trust_level=2)

    assert response.status_code == 200
    keycloak_client.add_user_to_groups.assert_called_once()

    row = conn.execute(
        "SELECT openmrs_id, trigger, trigger_src, action, status FROM audit_log"
    ).fetchone()
    assert row == ("jdoe", "workflow", DISCOURSE_BASE_URL, "keycloak_add_groups", "success")


def test_no_op_grant_when_already_trusted(client):
    test_client, conn = client
    keycloak_client = MagicMock()
    keycloak_client.add_user_to_groups.return_value = []
    keycloak_integration.set_client(keycloak_client)

    response = post_workflow_event(test_client, old_trust_level=2, new_trust_level=2)

    assert response.status_code == 200
    status = conn.execute("SELECT status FROM audit_log").fetchone()[0]
    assert status == "no_change"


def test_no_rule_matches_unreferenced_workflow_name(client):
    test_client, conn = client
    keycloak_client = MagicMock()
    keycloak_integration.set_client(keycloak_client)

    response = post_workflow_event(test_client, workflow_name="some-other-workflow")

    assert response.status_code == 200
    keycloak_client.add_user_to_groups.assert_not_called()
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0


def test_dry_run_records_dry_run_status_and_does_not_mutate_keycloak(tmp_path):
    test_client, conn = make_client(tmp_path, dry_run=True)
    with test_client:
        keycloak_client = MagicMock()
        keycloak_client.add_user_to_groups.return_value = ["jira-users", "confluence-users"]
        keycloak_integration.set_client(keycloak_client)

        response = post_workflow_event(test_client, old_trust_level=1, new_trust_level=2)

        assert response.status_code == 200
        status = conn.execute("SELECT status FROM audit_log").fetchone()[0]
        assert status == "dry_run"
        keycloak_client.add_user_to_groups.assert_called_once_with(
            "jdoe", ["jira-users", "jira-trunk-developer", "confluence-users"], dry_run=True
        )
    conn.close()
