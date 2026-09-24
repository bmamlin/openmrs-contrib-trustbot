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

## Manual testing with Slack

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

### Prepare test environment

1. Copy `.env.example` to `.env` and set:
  * KEYCLOAK_CLIENT_SECRET={Client Secret}
  * SLACK_BOT_TOKEN={Bot User OAuth Token}
  * SLACK_SIGNING_SECRET={Signing Secret}
  * CONFIG_PATH=./config/config.yaml
  * RULES_PATH=./config/rules.yaml
2. Copy `config/config.example.yaml` to `config/config.yaml` and set:
  * base_url: "http://localhost:8090"
  * realm: "master"
  * trusted_channel_id: "{Slack Channel ID}"
  * path: "./data/audit.db"
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


## Status

Early scaffolding — the rules engine, triggers, actions, and integrations
under `src/` are stubbed out with docstrings describing intended behavior.
See [openspec/specs/overview.md](openspec/specs/overview.md) for the full
functional and security requirements this project is being built against.
