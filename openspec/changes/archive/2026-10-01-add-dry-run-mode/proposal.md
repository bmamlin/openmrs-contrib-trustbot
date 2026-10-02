# Proposal

## Why

Per `overview.md` §6.5, the service needs a dry-run / simulation mode in
which all rule actions are evaluated and logged but no changes are made
to external systems (Keycloak). This lets an operator verify `rules.yaml`
changes, test a new trigger/action wiring, or validate the service end to
end against a real Discourse/Slack event — without risking an unwanted
Keycloak group change while doing so. It's the last unimplemented item
from the Functional/Security Requirements checklists; everything else in
§5–§6 is already built (see `CLAUDE.md`'s "Current state").

## What Changes

- Add a `dry_run` mode, off by default, that when enabled makes every
  matched rule's actions evaluate and audit-log as they normally would,
  but skip the actual external mutation (no Keycloak group add/remove
  call is made).
- Toggle via `config.yaml`'s new `dry_run: false` field (read once at
  startup, like the rest of `config.yaml`), with an optional `DRY_RUN`
  environment variable override (`true`/`false`, case-insensitive;
  blank/absent falls back to the config value) — the same
  env-var-overrides-config pattern already used for `LOG_LEVEL`.
- Extend the audit log's `status` column with a new value, `dry_run`,
  distinct from `success`/`no_change`/`failure`, so a simulated action is
  never mistaken for a real one in the audit trail.
- Update the three Slack command responses (`/trust`, `/revoke`) to say
  so explicitly when dry-run is active, so an operator testing the
  command doesn't mistake the simulated response for a real grant/revoke.
  (`/trust-status` is unaffected — it already never touches the rules
  engine.)
- Applies uniformly to every trigger path (the Discourse webhook and all
  Slack commands) — one process-wide mode, not a per-request flag.

## Capabilities

### New Capabilities
- `dry-run-mode`: the cross-cutting mode itself — how it's configured,
  that it applies uniformly to every trigger path, and the general
  contract that no external-system mutation occurs while it's active.

### Modified Capabilities
- `rules-engine`: "Every attempted action is audited" gains a dry-run
  outcome alongside success/no-op/failure.
- `audit-log`: "Status is constrained to known outcome values" gains
  `dry_run` as a fourth valid value.
- `keycloak-access-provisioning`: new requirement that `keycloak_add_groups`
  makes no Keycloak-side change when dry-run is active, while still
  reporting what it would have done.
- `keycloak-access-revocation`: same, for `keycloak_remove_groups`.
- `slack-trust-command`: "The caller receives a clear response for every
  valid command" gains a dry-run scenario.
- `slack-revoke-command`: same, for `/revoke`.

## Impact

- `src/config.py`: new `dry_run: bool = False` field on `ServiceConfig`.
- `src/main.py`: read `DRY_RUN` env var (blank-safe override, same
  pattern as `DISCOURSE_REPLAY_WINDOW_SECONDS`), pass the resolved
  boolean into `webhooks.create_webhooks_router(...)` and
  `create_slack_app(...)`.
- `src/engine/models.py`: `ActionResult.status` literal gains `"dry_run"`.
- `src/engine/evaluator.py`: `execute_rule()` accepts a `dry_run: bool`
  and passes it to each action executor.
- `src/actions/keycloak.py`: `add_groups`/`remove_groups` accept
  `dry_run`, compute the would-be diff without mutating when active.
- `src/integrations/keycloak.py`: `KeycloakClient.add_user_to_groups`/
  `remove_user_from_groups` accept `dry_run`, skip the actual
  `group_user_add`/`group_user_remove` calls when active (still reading
  current membership live, as always).
- `src/api/webhooks.py`, `src/integrations/slack.py`: thread `dry_run`
  through their contexts into `execute_rule()`; Slack response formatters
  gain dry-run wording.
- `src/audit/schema.sql`: update the `status` column's documentation
  comment (no actual schema change — it's an unconstrained `TEXT`
  column already).
