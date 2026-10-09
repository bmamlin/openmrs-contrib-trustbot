# CLAUDE.md

AI-assistant context for the OpenMRS Trust Bot repository.

## What this project is

A Python/FastAPI service that automates granting and revoking OpenMRS
community access (JIRA, Confluence via Keycloak groups) based on:

- **Discourse webhooks/Workflows** — automatic, named triggers declared
  in `rules.yaml` (e.g. a `"trusted"` Discourse Workflow, or a native
  `user_promoted` webhook event)
- **Slack slash commands** (`/trust`, `/trust-revoke`, `/trust-status`) — manual,
  human-in-the-loop, restricted to a designated private Slack channel

It is built around a generic, declarative **rules engine**: rules in
`rules.yaml` map triggers to actions (IFTTT-style). The engine core must
stay generic — new trigger/action types should be addable without
modifying `src/engine/`.

The full spec, config schema, and repo plan are the source of truth:

- [openspec/specs/overview.md](openspec/specs/overview.md) — problem statement, architecture, functional/security requirements
- [openspec/specs/config-schema.md](openspec/specs/config-schema.md) — `config.yaml` / `rules.yaml` schema
- [openspec/specs/repository-plan.md](openspec/specs/repository-plan.md) — repo structure rationale
- [openspec/specs/architecture.md](openspec/specs/architecture.md) — diagrams/data flow (in progress)

Read the spec before implementing a module — most modules under `src/`
are currently stubs whose docstrings summarize the relevant spec section,
but the spec itself is authoritative.

## Stack

- Python 3.12+, FastAPI, uvicorn
- `slack-bolt` (Slack), `python-keycloak` (Keycloak Admin REST API),
  `pydiscourse` (Discourse)
- PyYAML for config parsing
- SQLite (stdlib `sqlite3`) for the append-only audit log
- pytest / pytest-asyncio / httpx for testing

## Layout

```
src/config.py       loads config.yaml once at startup (ServiceConfig, Pydantic)
src/engine/         rules engine core: models (Pydantic), loader (rules.yaml), evaluator
src/triggers/       one module per trigger type (webhook, workflow, slack_trust_command, ...)
src/actions/        one module per action type (keycloak_add_groups, keycloak_remove_groups)
src/integrations/   external API clients (Keycloak, Discourse, Slack)
src/audit/          SQLite audit log (schema.sql + db.py)
src/api/            FastAPI routers (health, webhooks, admin)
config/             example config.yaml / rules.yaml (committed; live copies are host-mounted, gitignored)
tests/unit/         one test module per engine/trigger/action/integration module
tests/integration/  end-to-end rule evaluation pipeline
tests/security/     unauthorized channel, malformed/unsigned payloads, replay attacks, rate limiting
```

Trigger/action `type` strings (e.g. `"slack_trust_command"`,
`"keycloak_add_groups"`) are dispatched through registries in
`src/engine/evaluator.py` (`TRIGGER_MATCHERS`, `ACTION_EXECUTORS`),
populated by `src/triggers/register_all()` and `src/actions/register_all()`
— see those modules' docstrings and
`openspec/changes/archive/2026-09-24-add-slack-trust-grant/design.md`
for the mechanism. A trigger type referenced in `rules.yaml` but not yet
registered simply never matches, rather than erroring, so `rules.yaml` can
reference not-yet-implemented trigger types.

## Conventions

- **Config vs. code:** community-specific logic (which trust level grants
  which groups, etc.) belongs in `rules.yaml`, never hardcoded in `src/`.
- **Idempotency:** every action (`src/actions/`) must be safe to run
  repeatedly with the same input — check current state before mutating,
  and treat "already in desired state" as `status='no_change'`, not an
  error.
- **Audit everything:** every rule evaluation that attempts an action
  writes a row to `audit_log` (`src/audit/db.py`), including no-ops and
  failures. Audit rows are append-only — never UPDATE/DELETE.
- **Secrets:** only via environment variables (see `.env.example`); never
  in YAML, never logged, even at DEBUG.
- **Hot-reload semantics:** `rules.yaml` is re-read from disk on every
  trigger event (`src/engine/loader.py`); `config.yaml` is loaded once at
  startup and requires a restart to change.
- **Live state, not cache:** Keycloak group membership is always queried
  live (`src/integrations/keycloak.py`) — never cached or persisted
  locally.

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Current state

The rules engine core, the Slack `/trust`, `/trust-revoke`, and `/trust-status`
commands, the `keycloak_add_groups` / `keycloak_remove_groups` actions, the
Discourse webhook/workflow triggers, and the audit log are implemented
and tested (see `openspec/changes/archive/`) — `/trust <openmrs-id>` and
`/trust-revoke <openmrs-id>` in the configured Slack channel grant/revoke
Keycloak group access end-to-end, `/trust-status <openmrs-id>` reports
current Keycloak groups, Discourse trust level, and recent audit history
(read-only — it never reaches the rules engine, and degrades gracefully
per-section if one data source is unavailable), and `POST
/webhook/discourse` handles two distinct Discourse delivery mechanisms,
dispatched by rule data rather than hardcoded in service config:
`type: workflow, name: "<workflow-name>"` for a Discourse Workflow's
HTTP action (identified by `X-Discourse-Workflow`, HMAC-verified via
`DISCOURSE_WORKFLOW_SECRET` — any name a rule references is accepted,
not a single hardcoded one), and `type: webhook, name: "<event-type>"`
for a native Discourse webhook event (identified by
`X-Discourse-Event`, NOT `X-Discourse-Event-Type` — confirmed via live
capture that Type is only the coarse delivery category Discourse groups
events under, e.g. `user_badge_granted`/`user_badge_revoked` both send
`X-Discourse-Event-Type: user_badge`; only `X-Discourse-Event`
distinguishes them — HMAC-verified via `DISCOURSE_WEBHOOK_SECRET`;
supports `user_promoted` (resolves `username` directly from the
payload's embedded serialized user, confirmed via a live capture) and
`user_badge_granted`/`user_badge_revoked` (whose real Discourse payload
carries only a numeric user ID, never a username, confirmed via live
capture — there's an open Discourse Meta request to add one; until
then, a rule using either trigger fails loudly with a logged HTTP 400
rather than silently doing nothing, and will start working automatically
once Discourse ships the field) via a per-event-name parser registry in
`src/triggers/discourse_webhook.py` — an unrecognized event name is
acknowledged, not an error). There is deliberately no replay-window
check for either mechanism (removed — every action this service takes
is idempotent, so re-processing a replayed request is harmless; see
`openspec/changes/archive/*-restructure-discourse-triggers/design.md`).
Matching on anything beyond a trigger's `type`+`name` (e.g. payload
content, a future `condition` expression) is explicitly deferred. The
Discourse webhook and all three Slack commands are rate-limited
(in-memory, per-source-IP for the webhook, shared per-Slack-user-ID
across `/trust`/`/trust-revoke`/`/trust-status`) via
`src/ratelimit.py: RateLimiter`, with violations and the existing
channel-restriction rejections logged at WARNING level through a minimal
JSON logging setup (`src/logging_setup.py`, `LOG_LEVEL` env var). The
admin log-level API (`POST /admin/log-level`, bearer-token protected via
`ADMIN_API_TOKEN` when `config.yaml`'s `admin.require_auth` is true —
the default) changes the running process's log level at runtime without
a restart, reusing the same `src/logging_setup.py` logger. Dry-run mode
(`config.yaml`'s `dry_run`, overridable via `DRY_RUN`) makes every
trigger path — the Discourse webhook and all three Slack commands —
evaluate and audit-log rule actions as usual (status `dry_run`) without
making any actual Keycloak change; `/trust`/`/trust-revoke` responses disclose
this explicitly when active. DEBUG level (toggled via the admin endpoint
or `LOG_LEVEL`) now actually does something: every incoming POST's
headers (minus `Authorization`, via `src/logging_setup.py: redact_headers()`),
the rules engine's evaluation flow (`src/engine/evaluator.py`: which
event, which rules matched, every action attempted and its outcome —
generically, for every trigger/action type, logged once at these two
chokepoints rather than scattered across `src/triggers/`/`src/actions/`),
`rules.yaml` reloads, and Keycloak connectivity retries are all traced.
Native Discourse webhook bodies are deliberately not dumped raw (only
the already-curated `TriggerEvent` is); Slack's deprecated `token`
field is redacted the same way headers are. Every item in the spec's
Functional and Security Requirements checklists (§5–§6) is now
implemented.
