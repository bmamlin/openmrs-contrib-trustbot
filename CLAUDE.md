# CLAUDE.md

AI-assistant context for the OpenMRS Trust Bot repository.

## What this project is

A Python/FastAPI service that automates granting and revoking OpenMRS
community access (JIRA, Confluence via Keycloak groups) based on:

- **Discourse trust level webhooks** — automatic, when a user reaches
  trust level 2
- **Slack slash commands** (`/trust`, `/revoke`, `/trust-status`) — manual,
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
src/engine/        rules engine core: models (Pydantic), loader (rules.yaml), evaluator
src/triggers/       one module per trigger type (discourse_trust_level, slack_trust_command, ...)
src/actions/        one module per action type (keycloak_add_groups, keycloak_remove_groups)
src/integrations/   external API clients (Keycloak, Discourse, Slack)
src/audit/          SQLite audit log (schema.sql + db.py)
src/api/            FastAPI routers (health, webhooks, admin)
config/             example config.yaml / rules.yaml (committed; live copies are host-mounted, gitignored)
tests/unit/         one test module per engine/trigger/action module
tests/integration/  end-to-end rule evaluation pipeline
tests/security/     unauthorized channel, malformed/unsigned payloads, replay attacks, rate limiting
```

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

Repository scaffolding only. Engine/trigger/action/integration modules are
stubs (raise `NotImplementedError`) with docstrings describing intended
behavior per the spec. `GET /health` is the one fully implemented
endpoint. See the spec's Functional Requirements (§5) checklists for what
remains to be built.
