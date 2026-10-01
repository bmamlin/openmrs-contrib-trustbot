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
from src.ratelimit import RateLimiter

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


def make_client(*, rate_limiter=None):
    conn = get_connection(":memory:")
    router = create_webhooks_router(
        webhook_secret=WEBHOOK_SECRET,
        replay_window_seconds=REPLAY_WINDOW_SECONDS,
        workflow_name=WORKFLOW_NAME,
        discourse_base_url=DISCOURSE_BASE_URL,
        audit_conn=conn,
        rate_limiter=rate_limiter or RateLimiter(max_requests=1000, window_seconds=60),
    )
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), conn


@pytest.fixture
def client():
    test_client, conn = make_client()
    with test_client:
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


def test_request_within_rate_limit_proceeds_to_signature_verification():
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    test_client, conn = make_client(rate_limiter=limiter)
    with test_client:
        body = json.dumps(valid_payload()).encode()

        response = post(test_client, body, signature="sha256=" + "0" * 64)

        assert response.status_code == 403
        assert audit_row_count(conn) == 0


def test_request_exceeding_rate_limit_returns_429_before_signature_check():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    test_client, conn = make_client(rate_limiter=limiter)
    with test_client:
        body = json.dumps(valid_payload()).encode()
        bad_signature = "sha256=" + "0" * 64

        first = post(test_client, body, signature=bad_signature)
        assert first.status_code == 403

        second = post(test_client, body, signature=bad_signature)

        assert second.status_code == 429
        assert audit_row_count(conn) == 0


def test_rate_limit_keyed_by_first_x_forwarded_for_address():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    test_client, conn = make_client(rate_limiter=limiter)
    with test_client:
        body = json.dumps(valid_payload()).encode()
        bad_signature = "sha256=" + "0" * 64

        def post_with_forwarded_for(forwarded_for: str):
            return test_client.post(
                "/webhook/discourse",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Discourse-Workflow-Secret": bad_signature,
                    "X-Discourse-Workflow": WORKFLOW_NAME,
                    "X-Forwarded-For": forwarded_for,
                },
            )

        first = post_with_forwarded_for("203.0.113.5, 10.0.0.1")
        assert first.status_code == 403

        second = post_with_forwarded_for("203.0.113.5, 10.0.0.2")
        assert second.status_code == 429

        third = post_with_forwarded_for("198.51.100.9")
        assert third.status_code == 403
        assert audit_row_count(conn) == 0


def test_rate_limit_rejection_logs_warning_with_source_ip(client, caplog):
    test_client, conn = client
    limiter_client, limiter_conn = make_client(rate_limiter=RateLimiter(max_requests=0, window_seconds=60))
    with limiter_client:
        body = json.dumps(valid_payload()).encode()
        with caplog.at_level("WARNING"):
            response = limiter_client.post(
                "/webhook/discourse",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Discourse-Workflow-Secret": sign(body),
                    "X-Discourse-Workflow": WORKFLOW_NAME,
                    "X-Forwarded-For": "203.0.113.77",
                },
            )

        assert response.status_code == 429
        assert any(
            record.levelname == "WARNING" and "203.0.113.77" in record.message
            for record in caplog.records
        )


def test_invalid_signature_logs_warning(client, caplog):
    test_client, conn = client
    body = json.dumps(valid_payload()).encode()

    with caplog.at_level("WARNING"):
        response = post(test_client, body, signature="sha256=" + "0" * 64)

    assert response.status_code == 403
    assert any(record.levelname == "WARNING" for record in caplog.records)


def test_wrong_workflow_name_logs_warning(client, caplog):
    test_client, conn = client
    body = json.dumps(valid_payload()).encode()

    with caplog.at_level("WARNING"):
        response = post(test_client, body, signature=sign(body), workflow="some-other-workflow")

    assert response.status_code == 400
    assert any(record.levelname == "WARNING" for record in caplog.records)
