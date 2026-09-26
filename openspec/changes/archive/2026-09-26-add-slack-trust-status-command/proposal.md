# Proposal

## Why

ITSM currently has no quick way to check what access a given OpenMRS
community member actually has, or why — they'd have to check Keycloak's
admin console, Discourse, and (once this service is running) the audit
database separately. `/trust-status <openmrs-id>` is the third MVP Slack
command in the original spec (§5.3.1) and, unlike `/trust`/`/revoke`, is
explicitly read-only: it does not go through the rules engine at all. This
change implements it, aggregating Keycloak group membership, Discourse
trust level, and recent audit history into one Slack response.

## What Changes

- Implement `src/integrations/discourse.py: DiscourseClient` (currently
  `NotImplementedError`) — the first real Discourse integration in the
  codebase — with `get_trust_level(openmrs_id)` querying the Discourse API
  via `DISCOURSE_API_KEY` / `DISCOURSE_API_USERNAME`.
- Add a read function to `src/audit/db.py` to fetch the most recent
  `audit_log` rows for a given `openmrs_id` (the module is currently
  write-only — `get_connection()` + `record_event()`).
- Register a `/trust-status` command on the existing Slack Bolt app
  (alongside `/trust` and `/revoke`), reusing the same signature
  verification and channel-restriction model, but routing to a read/
  aggregate/respond path instead of the rules engine — no `TriggerEvent`,
  no `evaluate()`/`execute_rule()`.
- Reuse the existing `KeycloakClient.get_user_groups()` (already built and
  tested for `add_groups`/`remove_groups`) to list the target's current
  group memberships — no new Keycloak integration work.
- **Confirmed with user:** unlike `/trust`/`/revoke`, this command reads
  from three independent sources (Keycloak, Discourse, the audit DB). If
  one is unreachable, the command shows whatever data *is* available with
  a note on what's missing, rather than failing the whole command — a
  partial status view is more useful than none for a read-only ops
  command, and there's no state-change risk to protect against by
  aborting (unlike `/trust`/`/revoke`'s mutating actions). See `design.md`
  for the alternative considered.
- **Confirmed with user:** channel-restriction violations mirror
  `/trust`/`/revoke` exactly (silent rejection: no action, no response),
  rather than a visible error — because `/trust-status` displays
  potentially sensitive account history, and a visible rejection would be
  a new way to distinguish "this OpenMRS ID exists" from "it doesn't" to
  an unauthorized channel. See `design.md`.

Out of scope for this slice: the Discourse *webhook* trigger (a separate
future change — only needs signature verification and event parsing, not
this read API), rate limiting, the admin log-level API, dry-run mode, and
any change to `/trust` or `/revoke`'s existing behavior.

## Capabilities

### New Capabilities
- `slack-trust-status-command`: authorization (signing secret + channel
  restriction, mirroring `slack-trust-command`) for the `/trust-status`
  Slack command, and its read-only response behavior — aggregating
  Keycloak group membership, Discourse trust level, and recent audit
  history without invoking the rules engine.

### Modified Capabilities
(none — `audit-log`'s requirements are all about *writing* rows and don't
change to support a new *reader*; `keycloak-access-provisioning`'s
requirements are specific to the `keycloak_add_groups` action, and this
change only reuses an existing client method, not a new observable
behavior of that capability.)

## Impact

- New implementation (currently a stub) in:
  `src/integrations/discourse.py`.
- New function in `src/audit/db.py` (first read/query function in that
  module).
- `src/integrations/slack.py`: add a `/trust-status` command listener and
  its handler, alongside the existing `/trust` and `/revoke` ones on the
  same `App`/`SlackContext`.
- Requires `DISCOURSE_API_KEY` / `DISCOURSE_API_USERNAME` env vars at
  runtime (already documented in `.env.example`; previously unused by any
  code path).
- No `rules.yaml` or `config.yaml` schema changes.
- No changes to `/trust`, `/revoke`, the rules engine, or the audit
  table's write path.
- `src/api/webhooks.py`, `src/triggers/discourse.py`, and the Discourse
  webhook trigger remain stubs, untouched by this change.
