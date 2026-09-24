## Why

Granting OpenMRS community members JIRA/Confluence access today requires an ITSM
volunteer to manually add users to Keycloak groups. The project has a full spec
and repo scaffolding (stub modules) but no working code yet. This change
implements the first vertical slice — the generic rules engine plus the
`/trust` Slack command's full path through to a live Keycloak group grant — so
the core architecture (config → trigger → rule evaluation → action → audit) is
proven end-to-end before the remaining triggers (Discourse webhook, `/revoke`,
`/trust-status`) are built on top of it.

## What Changes

- Implement the generic rules engine: load and validate `rules.yaml` (re-read
  from disk on every trigger event per the hot-reload requirement), and
  evaluate a trigger event against all enabled rules using OR-logic across a
  rule's triggers, dispatching matched rules' actions by `type` without the
  engine knowing about specific trigger/action implementations.
- Implement the `slack_trust_command` trigger: verify the Slack request
  signature, reject commands issued outside the configured
  `slack.trusted_channel_id` (silently, no response), and turn a valid
  `/trust <openmrs-id>` command into a trigger event for the engine.
- Implement the `keycloak_add_groups` action and a Keycloak Admin REST API
  client: add the target OpenMRS ID to the rule's configured groups,
  idempotently (no-op if already a member), always querying Keycloak live
  (no local caching of membership), with the single-retry-then-fail behavior
  on Keycloak unavailability.
- Implement the append-only SQLite audit log: every rule evaluation that
  attempts an action (success, no-op, or failure) writes one `audit_log` row;
  no updates or deletes.
- Implement `config.yaml` loading at service startup (Keycloak base URL/realm,
  Slack trusted channel ID, database path) — loaded once, per the spec's
  hot-reload semantics (unlike `rules.yaml`).
- Wire the Slack Bolt app's `/trust` command handler and the rules engine into
  `src/main.py` so the FastAPI process serves a working `/trust` command.

Out of scope for this slice (deferred to future changes): `/revoke` and
`/trust-status` commands, the Discourse webhook trigger, rate limiting, the
admin log-level API, and dry-run/simulation mode.

## Capabilities

### New Capabilities
- `rules-engine`: loading `rules.yaml` and evaluating trigger events against
  rules to dispatch matching actions, generically across trigger/action types.
- `slack-trust-command`: authorization (signing secret + channel restriction)
  and parsing for the `/trust` Slack slash command, and its response behavior.
- `keycloak-access-provisioning`: idempotent, live-queried granting of
  Keycloak group membership via the `keycloak_add_groups` action.
- `audit-log`: append-only recording of every attempted rule action.

### Modified Capabilities
(none — no existing capability specs in this repository yet)

## Impact

- New implementations (currently stubs) in: `src/engine/models.py`,
  `src/engine/loader.py`, `src/engine/evaluator.py`, `src/triggers/slack.py`,
  `src/actions/keycloak.py`, `src/integrations/keycloak.py`,
  `src/integrations/slack.py`, `src/audit/db.py`.
- New: a `config.yaml` loader (service-level settings), and wiring in
  `src/main.py` to mount the Slack Bolt request handler alongside the
  existing `health` router.
- Runtime dependencies newly exercised: `slack-bolt`, `python-keycloak`
  (already in `requirements.txt`).
- Requires `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `KEYCLOAK_CLIENT_ID`,
  `KEYCLOAK_CLIENT_SECRET` env vars at runtime (already documented in
  `.env.example`) and a writable `/data/audit.db` (host-mounted volume in
  production; `./data/audit.db` locally).
- `src/api/webhooks.py` and the Discourse trigger/integration remain stubs,
  untouched by this change.
