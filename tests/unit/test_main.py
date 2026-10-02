"""Verifies the FastAPI app assembles and starts cleanly.

Uses a config file mirroring config/config.example.yaml but pointing
database.path at a temp directory (the example's /data/audit.db is a
container path, not writable outside Docker/production).
"""

import importlib
import sys

import pytest
from fastapi.testclient import TestClient

CONFIG_YAML = """
discourse:
  base_url: "https://talk.openmrs.org"
  webhook:
    replay_window_seconds: 300
    workflow_name: "trusted"
keycloak:
  base_url: "https://id-new.openmrs.org"
  realm: "OpenMRS"
  retry:
    max_retries: 1
    retry_delay_seconds: 2
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
    monkeypatch.setenv("ADMIN_API_TOKEN", "dummy-admin-token")

    sys.modules.pop("src.main", None)
    main = importlib.import_module("src.main")

    with TestClient(main.app) as client:
        yield client

    sys.modules.pop("src.main", None)


def test_app_starts_and_health_check_returns_200(app_client):
    response = app_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_app_starts_when_discourse_replay_window_env_var_is_blank(tmp_path, monkeypatch):
    # Regression test: `dotenv run` exports every key declared in .env, even
    # ones left blank (e.g. "DISCOURSE_REPLAY_WINDOW_SECONDS="), as an
    # actual empty-string env var -- not an absent one. os.environ.get()
    # only falls back to its default for a truly-absent key, so a naive
    # `int(os.environ.get("X", default))` crashes on int('') when X="".
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
    monkeypatch.setenv("DISCOURSE_REPLAY_WINDOW_SECONDS", "")
    monkeypatch.setenv("ADMIN_API_TOKEN", "dummy-admin-token")

    sys.modules.pop("src.main", None)
    main = importlib.import_module("src.main")
    try:
        with TestClient(main.app) as client:
            response = client.get("/health")
    finally:
        sys.modules.pop("src.main", None)

    assert response.status_code == 200
    assert main.app.state.audit_conn is not None


def test_app_fails_to_start_when_admin_auth_required_but_token_is_blank(tmp_path, monkeypatch):
    # admin.require_auth defaults to true (not set in CONFIG_YAML), so a
    # blank ADMIN_API_TOKEN must fail fast at startup -- an admin endpoint
    # that can never successfully authenticate is a misconfiguration.
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
    monkeypatch.delenv("ADMIN_API_TOKEN", raising=False)

    sys.modules.pop("src.main", None)
    try:
        with pytest.raises(RuntimeError, match="ADMIN_API_TOKEN"):
            importlib.import_module("src.main")
    finally:
        sys.modules.pop("src.main", None)
