# OpenMRS Trust Bot

Automates the elevation of OpenMRS community trust levels and downstream
access (JIRA, Confluence, via Keycloak groups) based on Discourse trust
signals and Slack-based human vouching — replacing the manual [Grant
Access to new users](https://github.com/openmrs/openmrs-contrib-itsmresources/wiki/Grant-Access-new-users)
ITSM runbook.

The service is a small, generic **rules engine** (IFTTT-style: triggers →
actions). All community-specific logic lives in YAML configuration
(`rules.yaml`), not in code — see
[openspec/specs/config-schema.md](openspec/specs/config-schema.md).

## Documentation

- [Project spec](openspec/specs/overview.md) — problem statement, architecture, requirements
- [YAML configuration schema](openspec/specs/config-schema.md) — `config.yaml` / `rules.yaml` reference
- [Repository structure plan](openspec/specs/repository-plan.md)
- [Architecture](openspec/specs/architecture.md) — diagrams, data flow (in progress)

See also [CLAUDE.md](CLAUDE.md) for AI-assistant context on this codebase.

## Requirements

- Python 3.12+
- Docker (for containerized deployment)

## Setup (local development)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env            # fill in secrets
cp config/config.example.yaml config/config.yaml
cp config/rules.example.yaml config/rules.yaml
```

Run the service:

```bash
uvicorn src.main:app --reload --port 8080
```

Run the test suite:

```bash
pytest
```

## Docker

```bash
docker compose up --build
```

`docker-compose.yml` mounts `./config` to `/config` (read-only) and
`./data` to `/data` inside the container, and reads secrets from `.env`.
In production these are host-mounted from `/opt/trustbot/config` and
`/opt/trustbot/data` respectively (see the spec's Host-Mounted Volumes
section) via the deployment's Terraform + Docker Compose configuration.

## Status

Early scaffolding — the rules engine, triggers, actions, and integrations
under `src/` are stubbed out with docstrings describing intended behavior.
See [openspec/specs/overview.md](openspec/specs/overview.md) for the full
functional and security requirements this project is being built against.
