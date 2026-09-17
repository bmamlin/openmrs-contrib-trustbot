# OpenMRS Trust Bot — Repository Structure Plan

> **Status:** Draft / Approved for implementation  
> **Last updated:** 2026-09-08  
> **Repository name:** `openmrs-contrib-trustbot`  
> **GitHub organization:** `openmrs`  

---

## Proposed Directory Structure

```
openmrs-contrib-trustbot/
│
├── openspec/                        # OpenSpec framework artifacts
│   ├── config.yaml                  # OpenSpec project settings & AI context
│   ├── specs/                       # Living specifications
│   │   ├── overview.md              # Main project spec (from openmrs-trust-automation-spec.md)
│   │   ├── config-schema.md         # YAML config schema (from openmrs-trustbot-config-schema.md)
│   │   └── architecture.md          # Future: diagrams, data flow, etc.
│   └── changes/                     # In-motion changes (OpenSpec workflow)
│       └── archive/                 # Completed changes move here
│
├── .claude/                         # OpenSpec workflow files for Claude Code
│   ├── skills/
│   └── commands/
│
├── config/                          # Example/template config files (safe to commit)
│   ├── config.example.yaml          # Annotated example of config.yaml
│   └── rules.example.yaml           # Annotated example of rules.yaml
│
├── data/                            # Placeholder — actual data is host-mounted at runtime
│   └── .gitkeep
│
├── src/                             # Application source
│   ├── main.py                      # Entrypoint — starts FastAPI app
│   ├── engine/                      # Rules engine core
│   │   ├── __init__.py
│   │   ├── loader.py                # YAML rules loading & hot-reload (re-reads rules.yaml on each event)
│   │   ├── evaluator.py             # Rule evaluation logic
│   │   └── models.py                # Trigger/action data models (Pydantic)
│   ├── triggers/                    # One module per trigger type
│   │   ├── __init__.py
│   │   ├── discourse.py             # discourse_trust_level trigger
│   │   └── slack.py                 # slack_trust_command, slack_revoke_command triggers
│   ├── actions/                     # One module per action type
│   │   ├── __init__.py
│   │   └── keycloak.py              # keycloak_add_groups, keycloak_remove_groups actions
│   ├── integrations/                # External API clients
│   │   ├── __init__.py
│   │   ├── keycloak.py              # Keycloak Admin REST API client (python-keycloak)
│   │   ├── discourse.py             # Discourse API client (pydiscourse)
│   │   └── slack.py                 # Slack client (slack-bolt)
│   ├── audit/                       # Audit log
│   │   ├── __init__.py
│   │   ├── db.py                    # SQLite connection and write logic
│   │   └── schema.sql               # Audit table DDL
│   └── api/                         # FastAPI routes
│       ├── __init__.py
│       ├── health.py                # GET /health — health check endpoint
│       ├── webhooks.py              # POST /webhook/discourse — Discourse webhook receiver
│       └── admin.py                 # Admin endpoints (log level control, future admin UI)
│
├── tests/                           # pytest test suite
│   ├── unit/
│   │   ├── engine/                  # Tests for loader, evaluator, models
│   │   ├── triggers/                # Tests for each trigger parser
│   │   └── actions/                 # Tests for each action executor
│   ├── integration/                 # End-to-end rule evaluation pipeline tests
│   └── security/                    # Security-focused tests:
│                                    #   - unauthorized Slack channel rejection
│                                    #   - malformed/unsigned webhook payloads
│                                    #   - replay attack simulation
│                                    #   - rate limit enforcement
│                                    #   - non-existent OpenMRS ID handling
│
├── Dockerfile                       # Production Docker image
├── docker-compose.yml               # Production reference compose file
├── docker-compose.override.yml      # Local dev overrides (gitignored)
├── .env.example                     # All required environment variables documented (no values)
├── requirements.txt                 # Runtime dependencies
├── requirements-dev.txt             # Dev/test dependencies (pytest, linting, etc.)
├── CLAUDE.md                        # AI context file: project overview, conventions, how to run tests
├── README.md                        # Human-facing project overview and setup guide
└── .gitignore
```

---

## Key Design Decisions

### Config vs. Data volumes
The repository contains **example** config files only (`config/config.example.yaml`,
`config/rules.example.yaml`). Live config and data are **host-mounted** into the container
at runtime and never committed to the repository:

| Host path (example) | Container path | Purpose |
|---|---|---|
| `/opt/trustbot/config/` | `/config/` | Live `config.yaml` and `rules.yaml` |
| `/opt/trustbot/data/` | `/data/` | SQLite audit database (`audit.db`) |

### Hot-reload behavior
- `rules.yaml` — re-read from `/config/` on every trigger event; changes take effect immediately
- `config.yaml` — loaded once at startup; changes require a container restart

### Environment variables
All secrets are injected via environment variables at runtime. See `.env.example` for the
full list. Key variables:

| Variable | Description |
|---|---|
| `DISCOURSE_WEBHOOK_SECRET` | Shared secret for Discourse webhook signature verification |
| `DISCOURSE_API_KEY` | Discourse API key (used by `/trust-status`) |
| `DISCOURSE_API_USERNAME` | Discourse username for the API key |
| `KEYCLOAK_CLIENT_ID` | Trust Bot service account client ID |
| `KEYCLOAK_CLIENT_SECRET` | Trust Bot service account client secret |
| `SLACK_BOT_TOKEN` | Slack Bot OAuth token (`xoxb-...`) |
| `SLACK_SIGNING_SECRET` | Slack signing secret for request verification |
| `ADMIN_API_TOKEN` | Bearer token for admin API endpoints |
| `LOG_LEVEL` | Application log level (`DEBUG`/`INFO`/`WARNING`/`ERROR`); overrides `config.yaml` |

### Tech stack
- **Language:** Python 3.12+
- **HTTP framework:** FastAPI
- **Slack:** slack-bolt
- **Keycloak:** python-keycloak
- **Discourse:** pydiscourse
- **Config parsing:** PyYAML or strictyaml
- **Database:** SQLite (via Python stdlib `sqlite3`)
- **Testing:** pytest
- **Deployment:** Docker container on OpenMRS OpenStack infrastructure

### OpenSpec integration
The `openspec/` folder follows the [OpenSpec](https://openspec.dev/) convention for
spec-driven development. Specs live in `openspec/specs/` and are versioned alongside the
code. The OpenSpec CLI (`openspec init`) should be run after the repository is created to
generate the appropriate workflow files for whichever AI coding tools are in use.

---

## Files to Copy Into Place at Setup

The following files were produced during the planning phase and should be placed into the
repository at the paths shown:

| Source file | Destination in repo |
|---|---|
| `openmrs-trust-automation-spec.md` | `openspec/specs/overview.md` |
| `openmrs-trustbot-config-schema.md` | `openspec/specs/config-schema.md` |
| `openmrs-trustbot-repo-plan.md` | `openspec/specs/repository-plan.md` (this file) |
