"""Security-focused tests for the admin log-level endpoint's authorization checks.

Through the real app (src.main), mirroring test_discourse_webhook.py's
pattern: confirms the full wiring (config + env vars + mounted route)
rejects as expected. Per the admin-log-level-api spec: a missing/invalid
bearer token is rejected (401) before the level is ever applied, and an
unrecognized level name is rejected (400) without affecting other routes.
"""

import importlib
import logging
import sys

import pytest
from fastapi.testclient import TestClient

ADMIN_API_TOKEN = "test-admin-token"

CONFIG_YAML = """
discourse:
  base_url: "https://talk.openmrs.org"
  webhook:
    replay_window_seconds: 300
    workflow_name: "trusted"
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
    monkeypatch.setenv("DISCOURSE_WORKFLOW_SECRET", "dummy-workflow-secret")
    monkeypatch.setenv("ADMIN_API_TOKEN", ADMIN_API_TOKEN)

    sys.modules.pop("src.main", None)
    main = importlib.import_module("src.main")

    original_level = logging.getLogger().level
    with TestClient(main.app) as client:
        yield client
    logging.getLogger().setLevel(original_level)

    sys.modules.pop("src.main", None)


def post_log_level(client: TestClient, level: str, *, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return client.post(f"/admin/log-level?level={level}", headers=headers)


def test_missing_token_is_rejected_and_health_is_unaffected(app_client):
    response = post_log_level(app_client, "DEBUG")

    assert response.status_code == 401

    health_response = app_client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}


def test_valid_token_and_recognized_level_succeeds(app_client):
    response = post_log_level(app_client, "DEBUG", token=ADMIN_API_TOKEN)

    assert response.status_code == 200
    assert response.json() == {"level": "DEBUG"}


def test_valid_token_and_unrecognized_level_is_rejected(app_client):
    response = post_log_level(app_client, "VERBOSE", token=ADMIN_API_TOKEN)

    assert response.status_code == 400
