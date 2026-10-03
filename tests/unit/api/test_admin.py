"""Unit tests for the admin log-level endpoint's authorization and validation.

Mirrors tests/unit/api/test_webhooks.py's style: an isolated router mounted
on a bare FastAPI app, not the real src.main app (that's covered by
tests/security/test_admin_log_level.py).
"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.admin import create_admin_router

ADMIN_API_TOKEN = "test-admin-token"


@pytest.fixture(autouse=True)
def reset_root_logger_level():
    root_logger = logging.getLogger()
    original_level = root_logger.level
    yield
    root_logger.setLevel(original_level)


def make_client(*, require_auth: bool):
    router = create_admin_router(admin_api_token=ADMIN_API_TOKEN, require_auth=require_auth)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def post_log_level(client, level: str, *, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.post(f"/admin/log-level?level={level}", headers=headers)


def test_valid_token_and_valid_level_changes_level_and_returns_it():
    client = make_client(require_auth=True)

    response = post_log_level(client, "DEBUG", token=ADMIN_API_TOKEN)

    assert response.status_code == 200
    assert response.json() == {"level": "DEBUG"}
    assert logging.getLogger().level == logging.DEBUG


def test_require_auth_false_allows_request_with_no_authorization_header():
    client = make_client(require_auth=False)

    response = post_log_level(client, "WARNING")

    assert response.status_code == 200
    assert response.json() == {"level": "WARNING"}
    assert logging.getLogger().level == logging.WARNING


def test_valid_token_and_invalid_level_returns_400_and_leaves_level_unchanged():
    client = make_client(require_auth=True)
    logging.getLogger().setLevel(logging.INFO)

    response = post_log_level(client, "VERBOSE", token=ADMIN_API_TOKEN)

    assert response.status_code == 400
    assert logging.getLogger().level == logging.INFO


def test_missing_authorization_header_returns_401():
    client = make_client(require_auth=True)

    response = post_log_level(client, "DEBUG")

    assert response.status_code == 401


def test_wrong_token_returns_401():
    client = make_client(require_auth=True)

    response = post_log_level(client, "DEBUG", token="wrong-token")

    assert response.status_code == 401


def test_rejection_logs_warning_without_leaking_any_token_value(caplog):
    client = make_client(require_auth=True)

    with caplog.at_level("WARNING"):
        response = post_log_level(client, "DEBUG", token="wrong-token")

    assert response.status_code == 401
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) >= 1
    for record in warnings:
        assert ADMIN_API_TOKEN not in record.message
        assert "wrong-token" not in record.message


def test_headers_logged_at_debug_with_authorization_redacted(caplog):
    client = make_client(require_auth=True)

    with caplog.at_level("DEBUG"):
        response = post_log_level(client, "DEBUG", token=ADMIN_API_TOKEN)

    assert response.status_code == 200
    debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
    assert any("authorization" in r.message for r in debug_records)
    for record in debug_records:
        assert ADMIN_API_TOKEN not in record.message


def test_headers_logged_at_debug_for_rejected_request_with_wrong_token_redacted(caplog):
    client = make_client(require_auth=True)

    with caplog.at_level("DEBUG"):
        response = post_log_level(client, "DEBUG", token="wrong-token")

    assert response.status_code == 401
    debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
    assert any("authorization" in r.message for r in debug_records)
    for record in debug_records:
        assert "wrong-token" not in record.message


def test_successful_level_change_logs_new_level_at_debug(caplog):
    client = make_client(require_auth=True)

    with caplog.at_level("DEBUG"):
        response = post_log_level(client, "DEBUG", token=ADMIN_API_TOKEN)

    assert response.status_code == 200
    debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
    assert any("DEBUG" in r.message and "changed" in r.message for r in debug_records)
