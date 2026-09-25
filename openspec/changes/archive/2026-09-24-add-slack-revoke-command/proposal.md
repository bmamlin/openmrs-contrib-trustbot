# Proposal

## Why

Access granted via `/trust` (or automatically at Discourse TL2) currently has
no way to be taken back short of an ITSM volunteer manually removing Keycloak
group memberships — the manual process this whole project exists to replace.
`/revoke` is one of the three MVP Slack commands in the original spec and was
scaffolded into `rules.yaml` from the start (`config/rules.example.yaml`
already has a "Revoke community edit access (manual /revoke)" rule), but the
trigger, action, and Keycloak client method it needs were left as
`NotImplementedError` stubs in the `add-slack-trust-grant` slice. This change
implements it — the mirror image of `/trust`, reusing the rules engine, audit
log, and Slack/Keycloak wiring already proven end-to-end for that command.

## What Changes

- Implement the `slack_revoke_command` trigger: same channel-restriction and
  signature-verification model as `slack_trust_command` (see the
  `slack-trust-command` capability), turning a valid
  `/revoke <openmrs-id>` command into a trigger event for the engine.
- Implement the `keycloak_remove_groups` action and the corresponding
  `KeycloakClient.remove_user_from_groups()` method: remove the target
  OpenMRS ID from the rule's configured groups, idempotently (no-op if the
  user already lacks all of them), always querying Keycloak live, with the
  same single-retry-then-fail behavior on Keycloak unavailability as
  `keycloak_add_groups`.
- Register a `/revoke` command listener on the existing Slack Bolt app
  (alongside `/trust`), wired through the same `load_rules()` →
  `evaluate()` → `execute_rule()` path, with equivalent response messages
  (revoked / already not trusted / user not found).
- No `rules.yaml` schema changes: `config/rules.example.yaml` already
  declares the revoke rule; this change makes the engine able to act on it.

Out of scope for this slice (deferred to future changes): `/trust-status`,
the Discourse webhook trigger, rate limiting, the admin log-level API,
dry-run/simulation mode, and self-elevation checks (still an open item per
the original spec §6.1 — the private-channel membership model remains the
primary control).

## Capabilities

### New Capabilities
- `slack-revoke-command`: authorization (signing secret + channel
  restriction) and parsing for the `/revoke` Slack slash command, and its
  response behavior. Mirrors `slack-trust-command`.
- `keycloak-access-revocation`: idempotent, live-queried removal of
  Keycloak group membership via the `keycloak_remove_groups` action.
  Mirrors `keycloak-access-provisioning`.

### Modified Capabilities
(none — `rules-engine`'s trigger/action dispatch and `audit-log`'s
recording behavior are already generic across trigger/action types and
need no requirement changes to cover `slack_revoke_command` /
`keycloak_remove_groups`.)

## Impact

- New implementations (currently stubs) in: `src/triggers/slack.py`
  (`matches_revoke`, a new `build_revoke_event`), `src/actions/keycloak.py`
  (`remove_groups`), `src/integrations/keycloak.py`
  (`remove_user_from_groups`).
- `src/triggers/__init__.py` and `src/actions/__init__.py`:
  register `"slack_revoke_command"` and `"keycloak_remove_groups"` in the
  existing `TRIGGER_MATCHERS` / `ACTION_EXECUTORS` registries — the
  registry mechanism itself (`src/engine/evaluator.py`) needs no changes.
- `src/integrations/slack.py`: add a `/revoke` command listener alongside
  the existing `/trust` one on the same Slack Bolt `App`.
- No new runtime dependencies, no config schema changes, no database
  schema changes.
- `src/api/webhooks.py`, `/trust-status`, and the Discourse
  trigger/integration remain stubs, untouched by this change.
