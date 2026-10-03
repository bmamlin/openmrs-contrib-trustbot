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
from src.logging_setup import configure_logging
from src.ratelimit import RateLimiter

config = load_config()
configure_logging(config.logging.level)

app = FastAPI(title="OpenMRS Trust Bot")

app.include_router(health.router)

_admin_api_token = os.environ.get("ADMIN_API_TOKEN", "").strip()
if config.admin.require_auth and not _admin_api_token:
    raise RuntimeError(
        "ADMIN_API_TOKEN must be set when admin.require_auth is true (config.yaml)"
    )
admin_router = admin.create_admin_router(
    admin_api_token=_admin_api_token,
    require_auth=config.admin.require_auth,
)
app.include_router(admin_router)

audit_conn = get_connection(config.database.path)
app.state.audit_conn = audit_conn

_dry_run_override = os.environ.get("DRY_RUN", "").strip().lower()
dry_run = (
    _dry_run_override in ("true", "1", "yes", "on") if _dry_run_override else config.dry_run
)

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

discourse_webhook_rate_limiter = RateLimiter(
    max_requests=config.rate_limiting.discourse_webhook.max_requests,
    window_seconds=config.rate_limiting.discourse_webhook.window_seconds,
)
webhooks_router = webhooks.create_webhooks_router(
    webhook_secret=os.environ["DISCOURSE_WEBHOOK_SECRET"],
    workflow_secret=os.environ["DISCOURSE_WORKFLOW_SECRET"],
    discourse_base_url=config.discourse.base_url,
    audit_conn=audit_conn,
    rate_limiter=discourse_webhook_rate_limiter,
    dry_run=dry_run,
)
app.include_router(webhooks_router)

slack_commands_rate_limiter = RateLimiter(
    max_requests=config.rate_limiting.slack_commands.max_requests,
    window_seconds=config.rate_limiting.slack_commands.window_seconds,
)
slack_app = create_slack_app(
    os.environ["SLACK_BOT_TOKEN"],
    os.environ["SLACK_SIGNING_SECRET"],
    trusted_channel_id=config.slack.trusted_channel_id,
    audit_conn=audit_conn,
    rate_limiter=slack_commands_rate_limiter,
    dry_run=dry_run,
)
app.state.slack_app = slack_app
_slack_handler = SlackRequestHandler(slack_app)


@app.post("/slack/commands")
async def slack_commands(request: Request):
    return await _slack_handler.handle(request)
