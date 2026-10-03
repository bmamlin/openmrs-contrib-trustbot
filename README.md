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
| `POST` | `/webhook/discourse` | Native Discourse webhooks and Discourse Workflow HTTP actions (HMAC-signed; see [Manual testing](#manual-testing)) |
| `POST` | `/admin/log-level` | Change the running log level at runtime (see [Change the log level at runtime](#change-the-log-level-at-runtime)) |

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

A **Discourse Workflow**'s HTTP action step can call the service's
`/webhook/discourse` endpoint for events Discourse's native webhooks
don't cover, or when you want full control over the payload shape.
Which workflow names matter — and what each one does — is declared in
`rules.yaml` (`type: workflow` triggers), not hardcoded in service
config, so any name you choose works as long as a rule references it.

1. In Discourse Admin > Plugins > Workflows, create a Workflow with:
  * A trigger condition for whatever event you want to react to (e.g.
    a user's trust level increasing from 0 or 1 to 2, 3, or 4)
  * A Code step (run before the HTTP request) that computes an
    HMAC-SHA256 signature of the request body, using a secret set as a
    workflow variable, and adds it as a custom header
    `X-Discourse-Workflow-Secret: sha256=<hex-digest>`. See 
    [here](https://meta.discourse.org/t/could-usernames-be-included-in-user-badge-webhook-payload/413448/16?u=burke) 
    for a description.
  * An HTTP request step POSTing to `https://example.ngrok-free.dev/webhook/discourse`
    (your ngrok URL + `/webhook/discourse`) with a JSON body that
    includes at minimum a top-level `username` field (required — this
    is the target OpenMRS ID); include whatever else your rule's
    action needs
  * A custom header `X-Discourse-Workflow-Secret` with value `{{ $("Code").item.json.signature }}`
  * A custom header `X-Discourse-Workflow` set to a name of your
    choosing (e.g. `trusted`) — this is the `name` your `rules.yaml`
    trigger (`type: workflow, name: "trusted"`) matches against
  * Content type `JSON`
  * Request body set to `{{ $("Code").item.json.payload }}`
  * Never error toggled on
2. Pick a secret for that Code step's HMAC key. Set this as the value
   of a Workflow variable with key `secret` and use the same 
   value as `DISCOURSE_WORKFLOW_SECRET` below (shared across every
   workflow name you configure, not scoped to one).

### Set up a native Discourse webhook

For event types Discourse already emits natively (`user_promoted`,
`user_badge_granted`, `user_badge_revoked`), a native webhook needs no
Workflow at all.

> [!NOTE]
> `user_badge_granted`/`user_badge_revoked` currently fail with a
> logged HTTP 400 — Discourse's payload for these two only carries a
> numeric user ID, never a username, so there's no way to resolve a
> target OpenMRS ID yet. There's an open Discourse Meta request to add
> one; `user_promoted` already works today since its payload includes
> the full serialized user.

1. In Discourse admin (Admin > Advanced > Webhooks), create a webhook:
  * Payload URL: your ngrok URL + `/webhook/discourse`
  * Secret: pick a value — this is what you'll set as
    `DISCOURSE_WEBHOOK_SECRET` below (shared across every event type
    you select, not scoped to one)
  * Under event types, select whichever of the three supported events
    you want (e.g. "user promoted")
2. Reference that event's name in `rules.yaml` as a `type: webhook`
   trigger, e.g. `type: webhook, name: "user_promoted"`.

See [the restructure-discourse-triggers design doc](openspec/changes/archive/2026-10-03-restructure-discourse-triggers/design.md)
for the full rationale behind this two-mechanism model.

### Prepare test environment

1. Copy `.env.example` to `.env` and set:
  * KEYCLOAK_CLIENT_SECRET={Client Secret}
  * SLACK_BOT_TOKEN={Bot User OAuth Token}
  * SLACK_SIGNING_SECRET={Signing Secret}
  * DISCOURSE_WORKFLOW_SECRET={the secret used in the Workflow's Code step}
  * DISCOURSE_WEBHOOK_SECRET={the secret set when creating the native webhook}
  * CONFIG_PATH=./config/config.yaml
  * RULES_PATH=./config/rules.yaml
2. Copy `config/config.example.yaml` to `config/config.yaml` and set:
  * `keycloak.base_url`: "http://localhost:8090"
  * `keycloak.realm`: "master"
  * `slack.trusted_channel_id`: "{Slack Channel ID}"
  * `database.path`: "./data/audit.db"
3. Copy `config/rules.example.yaml` to `config/rules.yaml` — its default
   `type: workflow, name: "trusted"` rule already matches the Workflow
   name chosen above

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

### Test the Discourse Workflow trigger

Verify groups for user `test2` in Keycloak is an empty list, and that
`test2` also exists as a Discourse user on your Discourse instance (its
username must match the Keycloak username exactly). Trigger whatever
condition your Workflow's trigger step is configured for (e.g. raising
`test2`'s Discourse trust level from below 2 to 2 or above). Your
configured Workflow should fire, and you should see the appropriate
groups added to the `test2` account in Keycloak — check `data/audit.db`
(as above) for a `workflow` row to confirm.

### Test a native Discourse webhook

Using the native webhook set up above (e.g. for `user_promoted`),
trigger the corresponding Discourse action for a test user whose
username matches a Keycloak account. Check `data/audit.db` for a
`webhook` row with the matching event name to confirm.

### Change the log level at runtime

`POST /admin/log-level?level=<LEVEL>` changes the running service's log
level without a restart. `<LEVEL>` is one of `DEBUG`, `INFO`, `WARNING`,
or `ERROR`, passed as a query parameter (not in the request body).

Authorization is a standard bearer token in the `Authorization` header,
set to your `.env`'s `ADMIN_API_TOKEN` value — not the body, and not a
custom header:

```bash
curl -X POST "http://localhost:8080/admin/log-level?level=DEBUG" \
  -H "Authorization: Bearer $ADMIN_API_TOKEN"
```

A successful request responds with the newly active level, e.g.
`{"level": "DEBUG"}`. A missing or incorrect token gets `401`; an
unrecognized level name gets `400` and leaves the current level
unchanged. Set `admin.require_auth: false` in `config.yaml` to skip the
token check entirely (local development only — never in production).

### Use DEBUG logging

Switch to `DEBUG` as above, then issue any command (`/trust test1`, a
Discourse Workflow/webhook event, or another `/admin/log-level` call)
and watch the service's stdout. You'll see: the request's headers
(`Authorization` and Slack's deprecated `token` field always show as
`"[REDACTED]"`, never their real value); which event was evaluated
against `rules.yaml` and which rules matched (or that none did); every
action attempted and its outcome; and, for Keycloak, any connectivity
retries. Discourse webhook request bodies are deliberately not dumped
raw — only the already-parsed event (username, trust level/badge ID)
is logged, to avoid ever logging a Discourse user's full profile data.
Switch back to `INFO` (or whatever level you run normally) when done.

### Test dry-run mode

Set `DRY_RUN=true` in `.env` (or `dry_run: true` in `config.yaml`) and
restart the service. Issue `/trust test1` as in [Test the `/trust`
command](#test-the-trust-command) above: the Slack response states the
grant was simulated and no real change was made, and `test1`'s Keycloak
groups are unchanged. Confirm via:

```bash
sqlite3 data/audit.db "select status from audit_log order by id desc limit 1;"
```

which should show `dry_run` rather than `success`. Set `DRY_RUN=false`
(or remove it) and restart to return to normal operation.

## Status

The rules engine core, the Slack `/trust`/`/revoke`/`/trust-status`
commands, the Discourse `webhook`/`workflow` triggers, the audit log,
rate limiting, the admin log-level API, dry-run mode, and DEBUG-level
logging are all implemented and tested — every item in the project
spec's Functional and Security Requirements checklists is now built. See
[openspec/specs/overview.md](openspec/specs/overview.md) for the full
functional and security requirements this project is being built against,
and [CLAUDE.md](CLAUDE.md) for a more detailed current-state summary.
