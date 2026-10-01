# Proposal

## Why

The last remaining MVP rule from the original spec — automatic access grant
when a community member reaches Discourse trust level 2 — has been
stubbed out (`src/api/webhooks.py`, `src/triggers/discourse.py`) since the
project began, waiting on a real, verified webhook mechanism. Investigation
during this change (see the conversation this proposal came out of) found
that stock Discourse webhooks have no trust-level-change event at all, and
the next-best alternative (the Discourse Automation plugin's
`user_badge_granted` event) would have required granting this service's
Discourse API credential admin-level access just to resolve a numeric user
ID to a username — a real privilege escalation worth avoiding. Discourse
Workflows (a newer Discourse feature, now configured and live-tested
against `talk.openmrs.org`) solves this cleanly: it already resolves the
username server-side and includes it directly in the webhook payload, so
no Discourse API credential is needed for this trigger at all.

## What Changes

- Implement `POST /webhook/discourse` (currently `NotImplementedError` in
  `src/api/webhooks.py`) to receive the Discourse Workflow's HTTP action
  payload: verify its HMAC-SHA256 signature, validate the configured
  workflow name, reject stale requests outside the replay window, parse
  the trust-level-change payload, and hand off to the rules engine.
- Implement `src/triggers/discourse.py`'s `discourse_trust_level` trigger:
  a matcher (fires when `new_trust_level >= threshold`, per the semantics
  already documented in `config-schema.md` and already present in
  `config/rules.example.yaml`) and a `TriggerEvent`-building function
  analogous to `src/triggers/slack.py`'s `build_trust_event()`.
- Register `discourse_trust_level` in `src/triggers/__init__.py`'s
  `register_all()` (not yet registered — currently a rule referencing it
  simply never matches, per the registry's documented behavior for
  unimplemented trigger types).
- Rename `DISCOURSE_WEBHOOK_SECRET` → `DISCOURSE_WORKFLOW_SECRET`
  throughout (`.env.example`, `config-schema.md`) — it's keyed against a
  secret the Discourse Workflow's own Code step computes an HMAC with, not
  a secret Discourse's native webhook system manages.
- Add a new `config.yaml` field, `discourse.webhook.workflow_name`, holding
  the expected `X-Discourse-Workflow` header value — this is a label the
  OpenMRS ITSM team chose when configuring their own Workflow, not a
  Discourse-defined constant, so it must be configurable, not hardcoded.
- Reuse, unchanged: the `keycloak_add_groups` action, the rules engine
  (`evaluate()`/`execute_rule()`), `load_rules()`, and the audit log
  (`record_event()`) — all already implemented and already handle
  everything this trigger needs once a `TriggerEvent` reaches them.

Out of scope for this slice: automatic revocation (Discourse doesn't
demote trust levels automatically in the first place; this remains manual
via `/revoke`, matching the original spec's resolved decision), rate
limiting on this endpoint (deferred in every prior change for the same
reason — a separate, cross-cutting concern), and anything about the
Discourse webhook signature/payload format originally assumed in
`overview.md` — that assumption turned out to be wrong and this proposal
supersedes it for the actual implementation (see Impact).

## Capabilities

### New Capabilities
- `discourse-trust-level-trigger`: signature verification, workflow-name
  validation, and replay protection for the Discourse Workflow webhook;
  parsing its payload into a trigger event; and the `discourse_trust_level`
  trigger's matching semantics. Dispatch into the rules engine and the
  `keycloak_add_groups` action are already covered by the existing
  `rules-engine` and `keycloak-access-provisioning` capabilities and need
  no changes.

### Modified Capabilities
(none — `rules-engine`, `keycloak-access-provisioning`, and `audit-log`'s
existing requirements already cover everything this trigger needs; this
change only adds a new way to produce a `TriggerEvent`, which those
capabilities are already generic over.)

## Impact

- New implementations (currently stubs) in: `src/api/webhooks.py`,
  `src/triggers/discourse.py`.
- `src/triggers/__init__.py`: register `discourse_trust_level`.
- `src/main.py`: construct whatever startup-time context the webhook
  handler needs (signature secret, replay window, expected workflow name,
  access to the audit connection and rules engine) — see `design.md` for
  how, since FastAPI route handlers aren't bundled into a stateful "app"
  object the way `slack-bolt`'s `App` is for the Slack commands.
- `.env.example` / `openspec/specs/config-schema.md`: rename
  `DISCOURSE_WEBHOOK_SECRET` → `DISCOURSE_WORKFLOW_SECRET`; document the
  new `discourse.webhook.workflow_name` config field; correct a
  pre-existing copy-paste error in `config-schema.md` where
  `replay_window_seconds`'s comment incorrectly says it "Corresponds to
  env var DISCOURSE_WEBHOOK_SECRET" (it doesn't — that's a separate
  field).
- No `rules.yaml` schema changes — `config/rules.example.yaml` already
  declares the matching rule from initial scaffolding.
- No changes to `/trust`, `/revoke`, `/trust-status`, or the
  `DISCOURSE_API_KEY`/`DISCOURSE_API_USERNAME`-based Discourse client
  (`src/integrations/discourse.py`) — that credential and client remain
  scoped to `/trust-status`'s trust-level lookup only, untouched and at
  its current (non-admin) privilege level.
- `openspec/specs/overview.md` is not edited by this change (consistent
  with how prior changes treated it as a historical planning document);
  its §3.1/§5.2 description of "Discourse webhooks" is superseded in
  practice by this change's actual mechanism, documented going forward in
  the new capability spec.
