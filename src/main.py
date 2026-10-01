"""OpenMRS Trust Bot — FastAPI application entrypoint.

Wires together the API routers (health, webhooks, admin) into a single
FastAPI app, and mounts the Slack `/trust` command behind
POST /slack/commands. Run with:

    uvicorn src.main:app --host 0.0.0.0 --port 8080

config.yaml is loaded once here at process startup (see src/config.py);
rules.yaml, by contrast, is re-read on every trigger event
(src/engine/loader.py). Secrets are read directly from environment
variables here and never stored in the config model.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from slack_bolt.adapter.fastapi import SlackRequestHandler

from src.api import admin, health, webhooks
from src.audit.db import get_connection
from src.config import load_config
from src.integrations import discourse as discourse_integration
from src.integrations import keycloak as keycloak_integration
from src.integrations.slack import create_slack_app

app = FastAPI(title="OpenMRS Trust Bot")

app.include_router(health.router)
app.include_router(admin.router)

config = load_config()

audit_conn = get_connection(config.database.path)
app.state.audit_conn = audit_conn

keycloak_client = keycloak_integration.build_client(
    config.keycloak.base_url,
    config.keycloak.realm,
    os.environ["KEYCLOAK_CLIENT_ID"],
    os.environ["KEYCLOAK_CLIENT_SECRET"],
    max_retries=config.keycloak.retry.max_retries,
    retry_delay_seconds=config.keycloak.retry.retry_delay_seconds,
)
keycloak_integration.set_client(keycloak_client)
app.state.keycloak_client = keycloak_client

discourse_client = discourse_integration.build_client(
    config.discourse.base_url,
    os.environ["DISCOURSE_API_KEY"],
    os.environ["DISCOURSE_API_USERNAME"],
)
discourse_integration.set_client(discourse_client)
app.state.discourse_client = discourse_client

_replay_window_override = os.environ.get("DISCOURSE_REPLAY_WINDOW_SECONDS", "").strip()
webhooks_router = webhooks.create_webhooks_router(
    webhook_secret=os.environ["DISCOURSE_WORKFLOW_SECRET"],
    replay_window_seconds=(
        int(_replay_window_override)
        if _replay_window_override
        else config.discourse.webhook.replay_window_seconds
    ),
    workflow_name=config.discourse.webhook.workflow_name,
    discourse_base_url=config.discourse.base_url,
    audit_conn=audit_conn,
)
app.include_router(webhooks_router)

slack_app = create_slack_app(
    os.environ["SLACK_BOT_TOKEN"],
    os.environ["SLACK_SIGNING_SECRET"],
    trusted_channel_id=config.slack.trusted_channel_id,
    audit_conn=audit_conn,
)
app.state.slack_app = slack_app
_slack_handler = SlackRequestHandler(slack_app)


@app.post("/slack/commands")
async def slack_commands(request: Request):
    return await _slack_handler.handle(request)
