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

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Health check (Docker/monitoring) |
| `POST` | `/slack/commands` | Slack slash commands — `/trust`, `/revoke`, `/trust-status` |
| `POST` | `/webhook/discourse` | Discourse Workflow trust-level trigger (HMAC-signed; see [Manual testing](#manual-testing)) |

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

## Manual testing

### Set up a development Keycloak instance locally

```bash
docker run --name mykeycloak -p 127.0.0.1:8090:8080 \
        -e KC_BOOTSTRAP_ADMIN_USERNAME=admin -e KC_BOOTSTRAP_ADMIN_PASSWORD=change_me \
        quay.io/keycloak/keycloak:latest \
        start-dev
```

Find Keycloak running at http://localhost:8090 and log in with admin/change_me, then:

1. Add client
  * Client type: OpenID Connect
  * Client ID: trustbot
  * Enable Client authentication
  * Enable Service account roles
2. In Credentials tab, copy Client Secret
3. In Service account roles tab, assign client roles `query-users`, `view-users`, `manage-users`, and `view-groups`
4. Add test users `test1` and `test2`
5. Add groups `confluence-users` `jira-trunk-developer` `jira-users`

### Set up Slack

In a new terminal window, publish the service port:
```bash
ngrok http 8080
```
This screen should give you the published URL you will need when 
setting up the Slack app.

1. Create private Slack channel
2. Copy its Channel ID
3. Create Slack app
  * Disable Socket Mode
  * Add Slash Command for `/trust` with Request URL `https://example.ngrok-free.dev/slack/commands` (adding `/slack/commands` to URL from ngrok in terminal)
  * Set Usage Hint to `openmrs-id`
  * Copy Signing Secret from Basic Information section
  * Copy Bot User OAuth Token from Install App section

### Set up a Discourse Workflow

Discourse's native, per-event webhooks have no trust-level-change event —
this uses a **Discourse Workflow** instead, configured on the Discourse
instance itself (e.g. `talk.openmrs.org`), to call the service's
`/webhook/discourse` endpoint when a user crosses trust level 2.

1. In Discourse admin, create a Workflow with:
  * A trigger that fires when a user's trust level increases from 0 or 1
    to 2, 3, or 4
  * An HTTP action step posting to `https://example.ngrok-free.dev/webhook/discourse`
    (your ngrok URL + `/webhook/discourse`) with a JSON body containing
    `username`, `old_trust_level`, `new_trust_level`, and `timestamp`
    (ISO 8601 UTC)
  * A custom header `X-Discourse-Workflow` set to a name of your choosing
    (e.g. `trusted`) — this must match `discourse.webhook.workflow_name`
    in `config.yaml`
  * A Code step (run before the HTTP action) that computes an
    HMAC-SHA256 signature of the request body, using a secret set as a
    workflow variable, and adds it as a custom header
    `X-Discourse-Workflow-Secret: sha256=<hex-digest>`
2. Pick a secret for that Code step's HMAC key — this is the value
   you'll set as `DISCOURSE_WORKFLOW_SECRET` below.

See [the add-discourse-trust-level-trigger design doc](openspec/changes/archive/2026-10-02-add-discourse-trust-level-trigger/design.md)
for the full rationale and exact payload/header shape this service expects.

### Prepare test environment

1. Copy `.env.example` to `.env` and set:
  * KEYCLOAK_CLIENT_SECRET={Client Secret}
  * SLACK_BOT_TOKEN={Bot User OAuth Token}
  * SLACK_SIGNING_SECRET={Signing Secret}
  * DISCOURSE_WORKFLOW_SECRET={the secret used in the Workflow's Code step}
  * CONFIG_PATH=./config/config.yaml
  * RULES_PATH=./config/rules.yaml
2. Copy `config/config.example.yaml` to `config/config.yaml` and set:
  * `keycloak.base_url`: "http://localhost:8090"
  * `keycloak.realm`: "master"
  * `slack.trusted_channel_id`: "{Slack Channel ID}"
  * `discourse.webhook.workflow_name`: the `X-Discourse-Workflow` value
    you chose above (e.g. "trusted")
  * `database.path`: "./data/audit.db"
3. Copy `config/rules.example.yaml` to `config/rules.yaml`

### Start the trustbot service

In the root folder:

```bash
source .venv/bin/activate
dotenv run -- uvicorn src.main:app --reload --port 8080
```

> [!TIP]
> FYI - When done, use Ctrl-C to stop the service and use the 
> command `deactivate` to exit the python virtual environment.

### Test the `/trust` command

Verify groups for user `test1` in Keycloak is an empty list. You 
should now be able to go into your private Slack channel and issue 
the command `/trust test1`. You should see the appropriate groups 
added to the `test1` account in Keycloak and get a success reply 
in Slack.

You can view logged events with:

```bash
sqlite3 data/audit.db "select * from audit_log;"
```

### Test the Discourse trust-level trigger

Verify groups for user `test2` in Keycloak is an empty list, and that
`test2` also exists as a Discourse user on your Discourse instance (its
username must match the Keycloak username exactly). Raise `test2`'s
Discourse trust level from below 2 to 2 or above (e.g. via the Discourse
admin console, or by meeting the trust level 2 activity requirements
naturally). Your configured Workflow should fire, and you should see the
appropriate groups added to the `test2` account in Keycloak — check
`data/audit.db` (as above) for a `discourse_trust_level` row to confirm.

## Status

The rules engine core, the Slack `/trust`/`/revoke`/`/trust-status`
commands, the Discourse trust-level webhook trigger, and the audit log
are implemented and tested. Rate limiting, the admin log-level API, and
dry-run mode remain stubbed out. See
[openspec/specs/overview.md](openspec/specs/overview.md) for the full
functional and security requirements this project is being built against,
and [CLAUDE.md](CLAUDE.md) for a more detailed current-state summary.
