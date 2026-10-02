"""Loads config.yaml — service-level settings, read once at startup.

Unlike rules.yaml (re-read on every trigger event, see
src/engine/loader.py), config.yaml is parsed once when the service starts;
changing it requires a restart. Mirrors the schema documented in
openspec/specs/config-schema.md. Secrets are never part of this model —
they are read directly from environment variables by the callers that
need them (see src/main.py).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class DiscourseWebhookConfig(BaseModel):
    replay_window_seconds: int = 300
    # The expected X-Discourse-Workflow header value — a label chosen when
    # configuring the Discourse Workflow, not a Discourse-defined
    # constant, so required rather than defaulted: a missing value should
    # fail config loading, not silently accept every workflow name.
    workflow_name: str


class DiscourseConfig(BaseModel):
    base_url: str
    webhook: DiscourseWebhookConfig


class KeycloakRetryConfig(BaseModel):
    max_retries: int = 1
    retry_delay_seconds: int = 2


class KeycloakConfig(BaseModel):
    base_url: str
    realm: str
    retry: KeycloakRetryConfig = KeycloakRetryConfig()


class SlackConfig(BaseModel):
    trusted_channel_id: str


class RateLimitRule(BaseModel):
    max_requests: int
    window_seconds: int


class RateLimitingConfig(BaseModel):
    discourse_webhook: RateLimitRule
    slack_commands: RateLimitRule


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: str = "json"


class DatabaseConfig(BaseModel):
    path: str = "/data/audit.db"


class AdminConfig(BaseModel):
    port: int = 8080
    require_auth: bool = True


class ServiceConfig(BaseModel):
    discourse: DiscourseConfig
    keycloak: KeycloakConfig
    slack: SlackConfig
    rate_limiting: RateLimitingConfig
    logging: LoggingConfig = LoggingConfig()
    database: DatabaseConfig = DatabaseConfig()
    admin: AdminConfig = AdminConfig()
    dry_run: bool = False


def default_config_path() -> Path:
    """The config.yaml path to use when none is given: $CONFIG_PATH, else /config/config.yaml."""
    return Path(os.environ.get("CONFIG_PATH", "/config/config.yaml"))


def load_config(path: Path | str | None = None) -> ServiceConfig:
    """Read and parse config.yaml into a validated ServiceConfig.

    Intended to be called once at service startup (see src/main.py), not
    on every request.
    """
    resolved = Path(path) if path is not None else default_config_path()
    with open(resolved) as f:
        raw = yaml.safe_load(f)
    return ServiceConfig.model_validate(raw)
