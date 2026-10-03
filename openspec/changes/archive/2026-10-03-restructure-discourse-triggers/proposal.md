# Proposal

## Why

The service was built around the expectation that Discourse would send a
webhook and the rule's job would be to interpret the payload data (e.g. a
trust-level-change event, filtered by an `old`/`new` threshold). What
actually shipped is a different pattern: Discourse POSTs are identified by
*which* webhook or Workflow sent them — `X-Discourse-Event` for native
webhooks, `X-Discourse-Workflow` for Discourse Workflows — and the rule's
job is really to say "when *this named thing* fires, do *that* action."
Today that identification is hardcoded: the one Workflow name the service
will ever accept (`"trusted"`) lives in `config.yaml` and is enforced in
`src/api/webhooks.py` *before* the event ever reaches `rules.yaml` — a
rule referencing `discourse_trust_level` has no way to know, or say, which
Workflow produced it. This also means only one Workflow can ever be
configured, and native Discourse webhooks (which, as of current Discourse,
support `user_promoted`, `user_badge_granted`, and `user_badge_revoked` —
contradicting this project's original research that no such events exist
at all) aren't usable as a trigger source at all. (Live verification
during this change found `user_promoted`'s payload does resolve a
username directly; the two badge events currently don't — see Impact.)

## What Changes

- Replace the `discourse_trust_level` trigger type with two generic
  trigger types, matched purely by `type` + `name` (no payload-content
  matching, no threshold/condition logic — deferred to a future
  `condition`-style enhancement):
  - `type: webhook, name: <event-type>` — a native Discourse webhook,
    identified by its `X-Discourse-Event` header (NOT
    `X-Discourse-Event-Type`, which is only the coarse delivery
    category — confirmed via live capture that `user_badge_granted`
    and `user_badge_revoked` share the same `X-Discourse-Event-Type:
    user_badge`; only `X-Discourse-Event` distinguishes them). Ships
    with support for `user_promoted`, `user_badge_granted`, and
    `user_badge_revoked`.
  - `type: workflow, name: <workflow-name>` — a Discourse Workflow HTTP
    action, identified by its `X-Discourse-Workflow` header (the
    mechanism already in production, generalized from "the one
    hardcoded name" to "any name a rule references"). The existing
    `"trusted"` Workflow's behavior is preserved as a rule, not code.
- `POST /webhook/discourse` becomes mechanism-agnostic: it branches on
  which header is present, verifies the matching signature scheme
  (`X-Discourse-Event-Signature` + new `DISCOURSE_WEBHOOK_SECRET` for
  native webhooks; `X-Discourse-Workflow-Secret` + the existing
  `DISCOURSE_WORKFLOW_SECRET` for Workflows, unchanged), and hands off
  to the rules engine using only `type`+`name` — the route no longer
  hardcodes a single accepted name.
- **BREAKING**: Remove `config.yaml`'s `discourse.webhook.workflow_name`
  and `discourse.webhook.replay_window_seconds` fields, and the
  `DISCOURSE_REPLAY_WINDOW_SECONDS` env var. Replay-window / staleness
  checking is dropped entirely: every action this service takes
  (`keycloak_add_groups`/`keycloak_remove_groups`) is already idempotent,
  so re-processing a replayed or duplicate event is harmless, and neither
  native webhooks nor (going forward) Workflow payloads are expected to
  carry a timestamp field worth checking.
- **BREAKING**: Remove the `discourse_trust_level` rule trigger type.
  `config/rules.example.yaml`'s TL2-grant rule becomes
  `type: workflow, name: trusted` (same action, same live behavior,
  no Discourse-side reconfiguration needed).
- Add `DISCOURSE_WEBHOOK_SECRET` (new env var) for native-webhook
  signature verification — distinct from `DISCOURSE_WORKFLOW_SECRET`,
  matching how Discourse itself separates "a webhook's secret" (set once
  per webhook in Discourse's admin UI, shared across every event type
  that webhook delivers) from "a Workflow's secret" (whatever the
  Workflow's own HTTP action step is configured to compute).

Deferred (explicitly out of scope, flagged for a future change): matching
on payload or header *content* (e.g. a `condition` expression like
`old_trust_level < 2 && new_trust_level >= 2`) beyond simple `type`+`name`
equality. Not needed today — every example trigger source already fires
only for the event this service should act on.

## Capabilities

### New Capabilities
- `discourse-webhook-trigger`: native Discourse webhook signature
  verification (`X-Discourse-Event-Signature`), `type: webhook`
  trigger matching by event name, and payload parsing for the
  `user_promoted`, `user_badge_granted`, and `user_badge_revoked` event
  types.
- `discourse-workflow-trigger`: Discourse Workflow signature
  verification (`X-Discourse-Workflow-Secret`, the existing mechanism),
  `type: workflow` trigger matching by workflow name, and the
  `username`-at-top-level payload convention Workflow authors must
  follow.

### Modified Capabilities
(none — `rules-engine`, `audit-log`, `keycloak-access-provisioning`, and
`discourse-webhook-rate-limiting` are all already generic over trigger
type and need no requirement changes; rate limiting in particular stays
IP-based and mechanism-agnostic, unaffected by this change.)

### Removed Capabilities
- `discourse-trust-level-trigger`: fully superseded by
  `discourse-workflow-trigger` (for the existing "trusted" Workflow) and
  `discourse-webhook-trigger` (for native events going forward). See the
  spec delta for the specific requirements removed and their migration.

## Impact

- `src/config.py`: remove `DiscourseWebhookConfig`; `DiscourseConfig`
  becomes `{base_url: str}` only.
- `src/engine/models.py`: `TriggerEvent` gains `name: str | None = None`.
- `src/triggers/discourse.py` (deleted) → replaced by
  `src/triggers/discourse_webhook.py` and
  `src/triggers/discourse_workflow.py`, each with a `matches()` function
  and a `build_event()` function; `src/triggers/__init__.py` registers
  `"webhook"` and `"workflow"` instead of `"discourse_trust_level"`.
  Confirmed via live capture: `user_promoted`'s payload resolves a
  username directly (via the embedded serialized user); `user_badge_granted`/
  `user_badge_revoked` currently do not (only a numeric user ID) — per
  explicit direction, their parsers accept a forward-compatible
  top-level `username` field and raise (logged, HTTP 400) when it's
  absent, so a rule using either trigger fails loudly today and starts
  working automatically once Discourse adds the field (there's an open
  Discourse Meta request for this), with no code change needed here.
- `src/api/webhooks.py`: route handler rewritten to branch on which
  signature header is present; `WebhookContext` drops
  `replay_window_seconds`/`workflow_name`, gains a second secret.
- `src/main.py`: read `DISCOURSE_WEBHOOK_SECRET`; drop the
  `DISCOURSE_REPLAY_WINDOW_SECONDS` override logic entirely.
- `config/config.example.yaml`, `.env.example`, `config/rules.example.yaml`,
  `openspec/specs/config-schema.md`: updated to match.
- `openspec/specs/overview.md`, `repository-plan.md`, `CLAUDE.md`,
  `README.md`: updated — replay protection is removed from the
  project's stated requirements (with rationale), not just silently
  dropped.
- Broad test collateral: every fixture that sets
  `discourse.webhook.workflow_name` or `DISCOURSE_REPLAY_WINDOW_SECONDS`,
  or constructs a `discourse_trust_level` trigger/event, needs updating
  (unit, integration, and security tests across `tests/unit/`,
  `tests/integration/`, `tests/security/`).
