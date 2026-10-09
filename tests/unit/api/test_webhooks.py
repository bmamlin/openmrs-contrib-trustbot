"""Unit tests for the Discourse webhook endpoint's branching and rejection paths.

Each rejection case here should short-circuit before ever touching the
rules engine or writing an audit row — verified by asserting audit_log
stays empty. The full successful-request paths are covered by
tests/integration/test_discourse_workflow_flow.py and
test_discourse_webhook_flow.py instead, since those need a real
rules.yaml.
"""

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.webhooks import create_webhooks_router
from src.audit.db import get_connection
from src.ratelimit import RateLimiter

WEBHOOK_SECRET = "test-webhook-secret"
WORKFLOW_SECRET = "test-workflow-secret"
DISCOURSE_BASE_URL = "https://talk.openmrs.org"


def sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def workflow_payload(**overrides) -> dict:
    payload = {"username": "jdoe", "old_trust_level": 1, "new_trust_level": 2}
    payload.update(overrides)
    return payload


def make_client(*, rate_limiter=None):
    conn = get_connection(":memory:")
    router = create_webhooks_router(
        webhook_secret=WEBHOOK_SECRET,
        workflow_secret=WORKFLOW_SECRET,
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


def post_webhook(client, body: bytes, *, signature: str | None, event_name: str | None = "user_promoted"):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Discourse-Event-Signature"] = signature
    if event_name is not None:
        headers["X-Discourse-Event"] = event_name
    return client.post("/webhook/discourse", content=body, headers=headers)


def post_workflow(client, body: bytes, *, signature: str | None, workflow: str | None = "trusted"):
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Discourse-Workflow-Signature"] = signature
    if workflow is not None:
        headers["X-Discourse-Workflow"] = workflow
    return client.post("/webhook/discourse", content=body, headers=headers)


def audit_row_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]


# --- Request with neither header ---


def test_neither_header_present_returns_400(client):
    test_client, conn = client
    body = json.dumps({}).encode()

    response = test_client.post(
        "/webhook/discourse", content=body, headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 400
    assert audit_row_count(conn) == 0


# --- Native webhook branch ---


def test_webhook_invalid_signature_returns_403(client):
    test_client, conn = client
    body = json.dumps({"user": {"username": "jdoe"}}).encode()

    response = post_webhook(test_client, body, signature="sha256=" + "0" * 64)

    assert response.status_code == 403
    assert audit_row_count(conn) == 0


def test_webhook_missing_signature_header_returns_403(client):
    test_client, conn = client
    body = json.dumps({"user": {"username": "jdoe"}}).encode()

    response = post_webhook(test_client, body, signature=None)

    assert response.status_code == 403
    assert audit_row_count(conn) == 0


def test_webhook_malformed_json_returns_400(client):
    test_client, conn = client
    body = b"not json"

    response = post_webhook(test_client, body, signature=sign(body, WEBHOOK_SECRET))

    assert response.status_code == 400
    assert audit_row_count(conn) == 0


def test_unsupported_webhook_event_name_returns_200_without_action(client):
    test_client, conn = client
    body = json.dumps({"user": {"username": "jdoe"}}).encode()

    response = post_webhook(
        test_client, body, signature=sign(body, WEBHOOK_SECRET), event_name="some_unsupported_event"
    )

    assert response.status_code == 200
    assert audit_row_count(conn) == 0


def test_user_promoted_reaches_the_rules_engine(client, tmp_path, monkeypatch):
    empty_rules_path = tmp_path / "rules.yaml"
    empty_rules_path.write_text("rules: []\n")
    monkeypatch.setenv("RULES_PATH", str(empty_rules_path))

    test_client, conn = client
    body = json.dumps({"user_promoted": {"username": "jdoe", "trust_level": 2}}).encode()

    response = post_webhook(
        test_client, body, signature=sign(body, WEBHOOK_SECRET), event_name="user_promoted"
    )

    assert response.status_code == 200


def test_user_badge_granted_with_no_username_returns_400(client):
    test_client, conn = client
    # The real payload shape Discourse sends today (confirmed via live
    # capture) -- no username field anywhere.
    body = json.dumps(
        {"user_badge": {"id": 1, "badge_id": 2, "user_id": 3569, "granted_by_id": -1}}
    ).encode()

    response = post_webhook(
        test_client, body, signature=sign(body, WEBHOOK_SECRET), event_name="user_badge_granted"
    )

    assert response.status_code == 400
    assert audit_row_count(conn) == 0


def test_webhook_invalid_signature_logs_warning(client, caplog):
    test_client, conn = client
    body = json.dumps({"user": {"username": "jdoe"}}).encode()

    with caplog.at_level("WARNING"):
        response = post_webhook(test_client, body, signature="sha256=" + "0" * 64)

    assert response.status_code == 403
    assert any(record.levelname == "WARNING" for record in caplog.records)


# --- Workflow branch ---


def test_workflow_invalid_signature_returns_403(client):
    test_client, conn = client
    body = json.dumps(workflow_payload()).encode()

    response = post_workflow(test_client, body, signature="sha256=" + "0" * 64)

    assert response.status_code == 403
    assert audit_row_count(conn) == 0


def test_workflow_missing_signature_header_returns_403(client):
    test_client, conn = client
    body = json.dumps(workflow_payload()).encode()

    response = post_workflow(test_client, body, signature=None)

    assert response.status_code == 403
    assert audit_row_count(conn) == 0


def test_workflow_malformed_json_returns_400(client):
    test_client, conn = client
    body = b"not json"

    response = post_workflow(test_client, body, signature=sign(body, WORKFLOW_SECRET))

    assert response.status_code == 400
    assert audit_row_count(conn) == 0


def test_workflow_missing_username_returns_400(client):
    test_client, conn = client
    payload = workflow_payload()
    del payload["username"]
    body = json.dumps(payload).encode()

    response = post_workflow(test_client, body, signature=sign(body, WORKFLOW_SECRET))

    assert response.status_code == 400
    assert audit_row_count(conn) == 0


def test_any_workflow_name_is_accepted_at_the_signature_layer(client, tmp_path, monkeypatch):
    # No rule references "some-other-workflow", so it should reach the
    # rules engine and simply match nothing -- HTTP 200, not rejected
    # for the name itself (there is no single hardcoded accepted name).
    empty_rules_path = tmp_path / "rules.yaml"
    empty_rules_path.write_text("rules: []\n")
    monkeypatch.setenv("RULES_PATH", str(empty_rules_path))

    test_client, conn = client
    body = json.dumps(workflow_payload()).encode()

    response = post_workflow(
        test_client, body, signature=sign(body, WORKFLOW_SECRET), workflow="some-other-workflow"
    )

    assert response.status_code == 200


def test_workflow_invalid_signature_logs_warning(client, caplog):
    test_client, conn = client
    body = json.dumps(workflow_payload()).encode()

    with caplog.at_level("WARNING"):
        response = post_workflow(test_client, body, signature="sha256=" + "0" * 64)

    assert response.status_code == 403
    assert any(record.levelname == "WARNING" for record in caplog.records)


# --- Rate limiting (mechanism-agnostic, checked before any branching) ---


def test_request_within_rate_limit_proceeds_to_signature_verification():
    limiter = RateLimiter(max_requests=5, window_seconds=60)
    test_client, conn = make_client(rate_limiter=limiter)
    with test_client:
        body = json.dumps(workflow_payload()).encode()

        response = post_workflow(test_client, body, signature="sha256=" + "0" * 64)

        assert response.status_code == 403
        assert audit_row_count(conn) == 0


def test_request_exceeding_rate_limit_returns_429_before_signature_check():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    test_client, conn = make_client(rate_limiter=limiter)
    with test_client:
        body = json.dumps(workflow_payload()).encode()
        bad_signature = "sha256=" + "0" * 64

        first = post_workflow(test_client, body, signature=bad_signature)
        assert first.status_code == 403

        second = post_workflow(test_client, body, signature=bad_signature)

        assert second.status_code == 429
        assert audit_row_count(conn) == 0


def test_rate_limit_keyed_by_first_x_forwarded_for_address():
    limiter = RateLimiter(max_requests=1, window_seconds=60)
    test_client, conn = make_client(rate_limiter=limiter)
    with test_client:
        body = json.dumps(workflow_payload()).encode()
        bad_signature = "sha256=" + "0" * 64

        def post_with_forwarded_for(forwarded_for: str):
            return test_client.post(
                "/webhook/discourse",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Discourse-Workflow-Signature": bad_signature,
                    "X-Discourse-Workflow": "trusted",
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


def test_rate_limit_rejection_logs_warning_with_source_ip(caplog):
    limiter_client, limiter_conn = make_client(rate_limiter=RateLimiter(max_requests=0, window_seconds=60))
    with limiter_client:
        body = json.dumps(workflow_payload()).encode()
        with caplog.at_level("WARNING"):
            response = limiter_client.post(
                "/webhook/discourse",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Discourse-Workflow-Signature": sign(body, WORKFLOW_SECRET),
                    "X-Discourse-Workflow": "trusted",
                    "X-Forwarded-For": "203.0.113.77",
                },
            )

        assert response.status_code == 429
        assert any(
            record.levelname == "WARNING" and "203.0.113.77" in record.message
            for record in caplog.records
        )


# --- DEBUG request logging ---


def test_headers_logged_at_debug_for_accepted_request(client, tmp_path, monkeypatch, caplog):
    empty_rules_path = tmp_path / "rules.yaml"
    empty_rules_path.write_text("rules: []\n")
    monkeypatch.setenv("RULES_PATH", str(empty_rules_path))

    test_client, conn = client
    body = json.dumps(workflow_payload()).encode()

    with caplog.at_level("DEBUG"):
        response = post_workflow(test_client, body, signature=sign(body, WORKFLOW_SECRET))

    assert response.status_code == 200
    debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
    assert any("x-discourse-workflow" in r.message for r in debug_records)


def test_headers_logged_at_debug_for_signature_rejected_request(client, caplog):
    test_client, conn = client
    body = json.dumps(workflow_payload()).encode()

    with caplog.at_level("DEBUG"):
        response = post_workflow(test_client, body, signature="sha256=" + "0" * 64)

    assert response.status_code == 403
    debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
    assert any("x-discourse-workflow" in r.message for r in debug_records)


def test_headers_logged_at_debug_for_rate_limited_request(caplog):
    limiter_client, limiter_conn = make_client(rate_limiter=RateLimiter(max_requests=0, window_seconds=60))
    with limiter_client:
        body = json.dumps(workflow_payload()).encode()
        with caplog.at_level("DEBUG"):
            response = limiter_client.post(
                "/webhook/discourse",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Discourse-Workflow-Signature": sign(body, WORKFLOW_SECRET),
                    "X-Discourse-Workflow": "trusted",
                },
            )

        assert response.status_code == 429
        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        assert any("x-discourse-workflow" in r.message for r in debug_records)


def test_raw_body_never_appears_in_debug_logs(client, caplog):
    # Invalid signature -- rejected before the rules engine, so this
    # needs no RULES_PATH; the point is the raw body is never logged
    # regardless of how the request is handled.
    test_client, conn = client
    body = json.dumps({"username": "jdoe", "some_other_secret_looking_field": "zzz"}).encode()

    with caplog.at_level("DEBUG"):
        post_workflow(test_client, body, signature="sha256=" + "0" * 64)

    debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
    assert not any("some_other_secret_looking_field" in r.message for r in debug_records)
