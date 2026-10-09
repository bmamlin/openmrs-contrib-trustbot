# OpenMRS Trust Bot — YAML Configuration Schema

> **Status:** Draft / In Progress  
> **Last updated:** 2026-09-08

Configuration is split across two files in the mounted `/config/` directory:

| File | Purpose |
|---|---|
| `config.yaml` | Service-level settings (non-secret operational config) |
| `rules.yaml` | Rules engine definitions (triggers and actions) |

**Secrets** (API keys, signing secrets, passwords) are never stored in YAML files. They are
injected via environment variables at runtime and referenced by name in `config.yaml` where
needed for documentation purposes only.

---

## `config.yaml`

```yaml
# =============================================================================
# OpenMRS Trust Bot — Service Configuration
# =============================================================================

# -----------------------------------------------------------------------------
# Discourse integration
# -----------------------------------------------------------------------------
discourse:
  base_url: "https://talk.openmrs.org"

  # Discourse API credentials are supplied via environment variables:
  #   DISCOURSE_API_KEY
  #   DISCOURSE_API_USERNAME
  #
  # Webhook/Workflow signature verification secrets are supplied via:
  #   DISCOURSE_WEBHOOK_SECRET    (native Discourse webhooks)
  #   DISCOURSE_WORKFLOW_SECRET   (Discourse Workflow HTTP action steps)
  #
  # Which specific webhook event types or workflow names are acted on —
  # and what action each one triggers — is declared in rules.yaml
  # (type: webhook / type: workflow triggers), not here. Any name a rule
  # references is accepted; there is no single hardcoded name.

# -----------------------------------------------------------------------------
# Keycloak integration
# -----------------------------------------------------------------------------
keycloak:
  base_url: "https://id-new.openmrs.org"
  realm: "OpenMRS"

  retry:
    # Number of additional attempts after the first failure before giving up
    max_retries: 1
    # Seconds to wait between attempts
    retry_delay_seconds: 2

  # Keycloak service account credentials are supplied via environment variables:
  #   KEYCLOAK_CLIENT_ID
  #   KEYCLOAK_CLIENT_SECRET

# -----------------------------------------------------------------------------
# Slack integration
# -----------------------------------------------------------------------------
slack:
  # The private channel ID from which trust commands are accepted.
  # Commands issued from any other channel are rejected.
  trusted_channel_id: "C0123456789"

  # Slack app credentials are supplied via environment variables:
  #   SLACK_BOT_TOKEN
  #   SLACK_SIGNING_SECRET

# -----------------------------------------------------------------------------
# Rate limiting
# -----------------------------------------------------------------------------
rate_limiting:
  # Discourse webhook endpoint: max requests per window per source IP
  discourse_webhook:
    max_requests: 60
    window_seconds: 60

  # Slack commands: max commands per window per Slack user
  slack_commands:
    max_requests: 10
    window_seconds: 60

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging:
  # Application log level: DEBUG | INFO | WARNING | ERROR
  # Can also be set or overridden via LOG_LEVEL environment variable.
  # Can be changed at runtime via the admin API without restarting.
  level: "INFO"

  # Format for log output. 'json' recommended for production (Docker log
  # aggregation); 'text' may be easier for local development.
  format: "json"    # json | text

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------
database:
  # Path inside the container to the SQLite audit database.
  # Should be within the host-mounted /data/ volume.
  path: "/data/audit.db"

# -----------------------------------------------------------------------------
# Admin API
# (Exposes health check and runtime log level control)
# -----------------------------------------------------------------------------
admin:
  # Port the FastAPI service listens on
  port: 8080

  # Whether to require authentication on admin endpoints.
  # Always set to true in production.
  require_auth: true

  # Admin API credentials are supplied via environment variables:
  #   ADMIN_API_TOKEN

# -----------------------------------------------------------------------------
# Dry-run mode
# -----------------------------------------------------------------------------
# When true, every matched rule's actions are evaluated and logged to the
# audit log (status 'dry_run'), but no external system (e.g. Keycloak) is
# actually changed. Applies uniformly to the Discourse webhook and every
# Slack command. Can also be set or overridden via the DRY_RUN environment
# variable (true/false, case-insensitive); a blank/unset DRY_RUN falls back
# to this value.
dry_run: false
```

---

## `rules.yaml`

```yaml
# =============================================================================
# OpenMRS Trust Bot — Rules Configuration
# =============================================================================
#
# Rules are evaluated on every trigger event. Each rule specifies:
#   - One or more triggers (what causes this rule to fire)
#   - One or more actions (what happens when it fires)
#
# rules.yaml is re-read from disk on every trigger event, so rule changes
# take effect immediately without restarting the service.
# Note: config.yaml changes (URLs, rate limits, etc.) require a container restart.
#
# A rule fires when ANY of its listed triggers matches the incoming event
# (OR logic). AND logic (requiring multiple conditions to be true simultaneously)
# is not supported in the MVP but is noted as a future extension point.
# =============================================================================

rules:

  # ---------------------------------------------------------------------------
  # Automatically grant community edit access when a user reaches
  # Discourse Trust Level 2, via the "trusted" Discourse Workflow. Any
  # workflow name referenced here is accepted — there is no single
  # hardcoded name (see "Webhook and Workflow triggers" below).
  # ---------------------------------------------------------------------------
  - name: "Grant community edit access (Discourse TL2)"
    enabled: true
    triggers:
      - type: workflow
        name: "trusted"
    actions:
      - type: keycloak_add_groups
        groups:
          - jira-users
          - jira-trunk-developer
          - confluence-users

  # ---------------------------------------------------------------------------
  # Alternative: the same grant via Discourse's native `user_promoted`
  # webhook event instead of a Workflow.
  # ---------------------------------------------------------------------------
  # - name: "Grant community edit access (user_promoted webhook)"
  #   enabled: true
  #   triggers:
  #     - type: webhook
  #       name: "user_promoted"
  #   actions:
  #     - type: keycloak_add_groups
  #       groups:
  #         - jira-users
  #         - jira-trunk-developer
  #         - confluence-users

  # ---------------------------------------------------------------------------
  # Manually grant community edit access via Slack /trust command.
  # ---------------------------------------------------------------------------
  - name: "Grant community edit access (manual /trust)"
    enabled: true
    triggers:
      - type: slack_trust_command
    actions:
      - type: keycloak_add_groups
        groups:
          - jira-users
          - jira-trunk-developer
          - confluence-users

  # ---------------------------------------------------------------------------
  # Manually revoke community edit access via Slack /trust-revoke command.
  # ---------------------------------------------------------------------------
  - name: "Revoke community edit access (manual /trust-revoke)"
    enabled: true
    triggers:
      - type: slack_revoke_command
    actions:
      - type: keycloak_remove_groups
        groups:
          - jira-users
          - jira-trunk-developer
          - confluence-users
```

---

## Environment Variables Reference

All secrets and any settings that may differ between environments
(development, staging, production) are supplied via environment variables.
These are never stored in YAML files.

| Variable | Required | Description |
|---|---|---|
| `DISCOURSE_WORKFLOW_SECRET` | Yes | Shared secret used to verify every Discourse Workflow's HTTP action signature (`X-Discourse-Workflow-Secret`) — not scoped to one workflow name; which names are acted on is declared in `rules.yaml` |
| `DISCOURSE_WEBHOOK_SECRET` | Yes | Shared secret used to verify native Discourse webhook signatures (`X-Discourse-Event-Signature`) — which event types are acted on is declared in `rules.yaml` |
| `DISCOURSE_API_KEY` | Yes | Discourse API key for read access (used by `/trust-status`) |
| `DISCOURSE_API_USERNAME` | Yes | Discourse username associated with the API key |
| `KEYCLOAK_CLIENT_ID` | Yes | Client ID for the Trust Bot service account in Keycloak |
| `KEYCLOAK_CLIENT_SECRET` | Yes | Client secret for the Trust Bot service account |
| `SLACK_BOT_TOKEN` | Yes | Slack Bot OAuth token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Yes | Slack signing secret for request verification |
| `ADMIN_API_TOKEN` | Yes | Bearer token for the admin API endpoints |
| `LOG_LEVEL` | No | Overrides `logging.level` in `config.yaml` if set |
| `DRY_RUN` | No | Overrides `dry_run` in `config.yaml` if set (`true`/`false`, case-insensitive) |
| `CONFIG_PATH` | No | Path to `config.yaml`. Defaults to `/config/config.yaml` (the container mount path); `docker-compose.yml` always sets this explicitly to that same path, overriding `.env`, so this is only meaningful for local, non-Docker development |
| `RULES_PATH` | No | Path to `rules.yaml`. Defaults to `/config/rules.yaml` (the container mount path); `docker-compose.yml` always sets this explicitly to that same path, overriding `.env`, so this is only meaningful for local, non-Docker development |
| `DATABASE_PATH` | No | Overrides `database.path` in `config.yaml` if set. `docker-compose.yml` always sets this explicitly to the container mount path (`/data/audit.db`), overriding `.env`, so this is only meaningful for local, non-Docker development |

---

## Notes & Design Decisions

### Why two files?
Separating service config (`config.yaml`) from rules (`rules.yaml`) keeps
operational settings distinct from business logic. An ITSM member adding a
new rule only needs to edit `rules.yaml` and doesn't risk accidentally
changing a URL or rate limit.

### Hot-reload behavior
`rules.yaml` is re-read from disk on every trigger event. Rule changes
(adding, removing, enabling, disabling rules) take effect immediately without
restarting the service.

`config.yaml` is loaded once at startup. Changes to service-level settings
(URLs, rate limits, ports, etc.) require a container restart to take effect.
This is intentional — config changes are riskier and less frequent than rule
changes, and requiring a restart makes them a deliberate, visible operation.

### Trigger logic: OR vs. AND
In the MVP, multiple triggers within a rule use OR logic — the rule fires if
any trigger matches. This is sufficient for all current use cases. AND logic
(e.g. "Discourse TL2 AND at least one GitHub contribution") is a natural
future extension and should be accommodated in the schema by adding a
`match` field:

```yaml
# Future extension (not MVP):
triggers:
  match: all    # all | any (default: any)
  conditions:
    - type: workflow
      name: trusted
    - type: github_contribution
      min_commits: 1
```

### `enabled` flag
Each rule has an `enabled: true/false` flag, allowing a rule to be
temporarily disabled without deleting it — useful for testing or pausing
a rule during an incident.

### Webhook and Workflow triggers: matched by `type` + `name` only
`type: webhook` (a native Discourse webhook, identified by its
`X-Discourse-Event` header) and `type: workflow` (a Discourse
Workflow's HTTP action, identified by its `X-Discourse-Workflow` header)
both match purely on `name` equality — no payload-content matching.
There is no single hardcoded accepted name for either type; any name a
rule references is accepted. Payload/header *content* matching (e.g. a
future `condition` field evaluating something like
`"old_trust_level < 2 && new_trust_level >= 2"`) is explicitly deferred
— not needed today, since every configured trigger source already
fires only for the event this service should act on.

A `type: webhook` event name needs a parser registered in
`src/triggers/discourse_webhook.py` before it can be used (Discourse
defines that payload shape, not this project); an event name received
with no registered parser is acknowledged (HTTP 200) and ignored, not
treated as an error. A registered parser that cannot resolve a target
OpenMRS ID from the payload instead rejects with HTTP 400 — a real
error, logged, not a silent no-op. (Discourse's `user_badge_granted`/
`user_badge_revoked` webhook payloads currently carry only a numeric
user ID, never a username — there's an open Discourse Meta request to
add it; until then, a rule using either trigger will reject every
request with a clear "missing username" error rather than silently do
nothing, and will start working automatically once Discourse adds the
field.) A `type: workflow` payload just needs a top-level `username`
field — the Workflow author controls the rest of the shape.

### Sensitive data in YAML
YAML files are committed to version control. They must never contain secrets.
The environment variables table above defines all secret values; `config.yaml`
documents their names for reference but never their values.
