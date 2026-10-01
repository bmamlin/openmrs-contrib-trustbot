"""Unit tests for the Discourse webhook endpoint's rejection paths.

Each case here should short-circuit before ever touching the rules engine
or writing an audit row — verified by asserting audit_log stays empty.
The full successful-request path is covered by
tests/integration/test_discourse_trust_level_flow.py instead, since that
needs a real rules.yaml.
"""

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.webhooks import create_webhooks_router
from src.audit.db import get_connection

WEBHOOK_SECRET = "test-webhook-secret"
WORKFLOW_NAME = "trusted"
DISCOURSE_BASE_URL = "https://talk.openmrs.org"
REPLAY_WINDOW_SECONDS = 300


def sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def valid_payload(**overrides) -> dict:
    payload = {
        "username": "jdoe",
        "old_trust_level": 1,
        "new_trust_level": 2,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def client():
    conn = get_connection(":memory:")
    router = create_webhooks_router(
        webhook_secret=WEBHOOK_SECRET,
        replay_window_seconds=REPLAY_WINDOW_SECONDS,
        workflow_name=WORKFLOW_NAME,
        discourse_base_url=DISCOURSE_BASE_URL,
        audit_conn=conn,
    )
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as test_client:
        yield test_client, conn


def post(client, body: bytes, *, signature: str | None, workflow: str | None = WORKFLOW_NAME):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Discourse-Workflow-Secret"] = signature
    if workflow is not None:
        headers["X-Discourse-Workflow"] = workflow
    return client.post("/webhook/discourse", content=body, headers=headers)


def audit_row_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]


def test_invalid_signature_returns_403(client):
    test_client, conn = client
    body = json.dumps(valid_payload()).encode()

    response = post(test_client, body, signature="sha256=" + "0" * 64)

    assert response.status_code == 403
    assert audit_row_count(conn) == 0


def test_missing_signature_header_returns_403(client):
    test_client, conn = client
    body = json.dumps(valid_payload()).encode()

    response = post(test_client, body, signature=None)

    assert response.status_code == 403
    assert audit_row_count(conn) == 0


def test_wrong_workflow_name_returns_400(client):
    test_client, conn = client
    body = json.dumps(valid_payload()).encode()

    response = post(test_client, body, signature=sign(body), workflow="some-other-workflow")

    assert response.status_code == 400
    assert audit_row_count(conn) == 0


def test_malformed_json_returns_400(client):
    test_client, conn = client
    body = b"not json"

    response = post(test_client, body, signature=sign(body))

    assert response.status_code == 400
    assert audit_row_count(conn) == 0


def test_missing_required_field_returns_400(client):
    test_client, conn = client
    payload = valid_payload()
    del payload["username"]
    body = json.dumps(payload).encode()

    response = post(test_client, body, signature=sign(body))

    assert response.status_code == 400
    assert audit_row_count(conn) == 0


def test_timestamp_too_old_returns_400(client):
    test_client, conn = client
    old_timestamp = (datetime.now(UTC) - timedelta(seconds=REPLAY_WINDOW_SECONDS + 60)).isoformat()
    body = json.dumps(valid_payload(timestamp=old_timestamp)).encode()

    response = post(test_client, body, signature=sign(body))

    assert response.status_code == 400
    assert audit_row_count(conn) == 0


def test_timestamp_too_far_in_future_returns_400(client):
    test_client, conn = client
    future_timestamp = (datetime.now(UTC) + timedelta(seconds=REPLAY_WINDOW_SECONDS + 60)).isoformat()
    body = json.dumps(valid_payload(timestamp=future_timestamp)).encode()

    response = post(test_client, body, signature=sign(body))

    assert response.status_code == 400
    assert audit_row_count(conn) == 0
