# Design

## Context

`src/api/webhooks.py: create_webhooks_router()` currently mounts one
`POST /webhook/discourse` route that only understands one delivery
mechanism (a Discourse Workflow's HTTP action) and one hardcoded
workflow name (`config.yaml`'s `discourse.webhook.workflow_name`).
`src/triggers/discourse.py` has one trigger type, `discourse_trust_level`,
whose matcher reads a rule's `threshold` field. See proposal.md for why
this is being generalized and what native Discourse webhook events
(`user_promoted`, `user_badge_granted`, `user_badge_revoked`) turned out
to already support.

The project's established pattern for a route needing per-instance
config is a factory function + context dataclass
(`create_webhooks_router()`/`WebhookContext`, `create_slack_app()`/
`SlackContext`) — this change keeps that shape, just with a richer
context and a branching handler.

## Goals / Non-Goals

**Goals:**
- One `POST /webhook/discourse` route handles both delivery mechanisms,
  branching on which signature header is present.
- `type`+`name` is the only matching dimension for both new trigger
  types — no payload-content matching.
- Each native webhook event type's payload-parsing is isolated and
  independently extensible (adding a fourth supported event type later
  touches one new function + one registry entry, not the route
  handler).
- The existing "trusted" Workflow keeps working with zero Discourse-side
  reconfiguration — only `rules.yaml`/`config.yaml` change.

**Non-Goals:**
- Payload/header *content* matching (a `condition`-style trigger
  field) — explicitly deferred per proposal.md.
- Replay/staleness protection — explicitly removed per proposal.md
  (idempotent actions make it unnecessary).
- Any change to `/trust-status`'s `DiscourseClient`
  (`src/integrations/discourse.py`) — untouched, unrelated read path.
- Supporting every native Discourse webhook event type — only the three
  named in the proposal ship now; others can be added later the same
  way.

## Decisions

### One route, branching on which signature header is present
`discourse_webhook(request)` checks for `X-Discourse-Event` first (NOT
`X-Discourse-Event-Type` — confirmed via live capture that this is only
the coarse delivery category Discourse groups events under: both
`user_badge_granted` and `user_badge_revoked` carry
`X-Discourse-Event-Type: user_badge`, identical for both, while
`X-Discourse-Event` carries the actual event name and differs correctly
between them; `user_promoted` happens to have the same value in both
headers, which is how this was initially missed); if present, treats
the request as a native webhook (verify `X-Discourse-Event-Signature`
against `DISCOURSE_WEBHOOK_SECRET`).
Otherwise, checks for `X-Discourse-Workflow`; if present, treats it as a
Workflow request (verify `X-Discourse-Workflow-Secret` against
`DISCOURSE_WORKFLOW_SECRET`, unchanged from today). If neither header is
present: HTTP 400. Real Discourse never sends both, so no explicit
tie-breaking logic beyond "check native-webhook header first" is needed.
Alternative considered: two separate routes
(`/webhook/discourse/webhook`, `/webhook/discourse/workflow`). Rejected
— one URL to configure in both Discourse's webhook admin UI and the
Workflow's HTTP action step is simpler ops, and the branching logic is a
handful of lines either way.

### `TriggerEvent` gains a `name` field; one generic matcher for both types
`src/engine/models.py: TriggerEvent` gains `name: str | None = None`.
Both `discourse_webhook.matches()` and `discourse_workflow.matches()`
are the same one-line check —
`trigger.type == event.type and trigger.name == event.name` — registered
separately for `"webhook"` and `"workflow"` since `register_action`/
`register_trigger` key by type string, but sharing one implementation
(a single `matches_by_name()` helper both modules import, or a shared
`src/triggers/_discourse_common.py` — implementation detail to settle
during apply). This mirrors how `discourse_trust_level`'s `threshold`
was a trigger-specific matching detail the generic engine never needed
to know about — `name`-matching is the same shape, just for two trigger
types instead of one.

### Per-event-type payload parser registry (native webhooks only)
`src/triggers/discourse_webhook.py` holds
`PAYLOAD_PARSERS: dict[str, Callable[[dict], tuple[str, dict]]]`, one
entry per supported `X-Discourse-Event` value, each returning
`(openmrs_id, normalized_payload)` from Discourse's raw JSON body — or
raising `ValueError` if the payload doesn't actually contain enough to
resolve a target OpenMRS ID (see the badge-event decision below). The
route handler looks up the event name; a miss means "acknowledge with
200, do nothing" (see next decision) rather than an error, but a
registered parser raising is a real error (HTTP 400). Workflow
payloads need no such registry — `discourse_workflow.py`'s `build_event()`
is one function for every workflow name, since the Workflow author (the
OpenMRS team, via the HTTP action step) fully controls the payload shape
and is expected to always include a top-level `username`. Alternative
considered: one parser per Workflow name too, mirroring the webhook
side. Rejected — unlike Discourse's native payload shapes (fixed,
outside this project's control), the Workflow's payload shape is
already whatever the OpenMRS team designs it to be, so a single
"require `username`, pass the rest through" contract is sufficient and
keeps adding a new Workflow name a pure `rules.yaml`+Discourse-admin
change, no code change.

### An unsupported/unmatched event type is HTTP 200, not an error
Both new trigger types treat "no parser registered" (webhook) or "no
rule references this name" (either type) as a normal, successful
no-op — HTTP 200, no action. This matters because Discourse's native
webhook admin UI lets an operator select broad event categories (e.g.
"all user events") rather than cherry-picking exactly the three this
service parses; rejecting those as errors would make webhook
configuration needlessly fragile. It also matches the existing "unknown
trigger type never matches, doesn't error" convention already
documented for `rules.yaml` (`CLAUDE.md`, `src/engine/evaluator.py`'s
`_trigger_matches()`).

### Badge events: accept a forward-compatible `username`, fail loudly without one
Live capture confirmed `user_promoted`'s payload embeds the full
serialized user (including `username`) under `payload["user_promoted"]`,
but `user_badge_granted`/`user_badge_revoked`'s payload
(`payload["user_badge"]`) carries only numeric `user_id`, `badge_id`,
and timestamps — no username at all, and there's an open Discourse Meta
request asking Discourse to add one. Per explicit direction: assume
`username` may eventually appear in the payload (checked at both the
top level and inside `user_badge`, in case Discourse adds it in either
position) and raise `ValueError` when it's absent, rather than treating
the event as unsupported (which would silently no-op). This means a
rule using either badge trigger fails loudly today (HTTP 400, logged)
explaining why, and will start working the moment Discourse ships the
field — no code change needed here. Alternative considered: treat badge
events as entirely unsupported (return `None` from `build_event()`,
same as an unregistered name) until Discourse adds the field. Rejected
— that would hide a configuration mistake (a rule referencing a trigger
that can never fire) behind the same "silent no-op" behavior reserved
for "Discourse sent an event type we don't care about"; failing loudly
makes the actual blocker visible in logs instead.

### Two secrets, one per delivery mechanism
`DISCOURSE_WEBHOOK_SECRET` (new) verifies every native webhook event
type; `DISCOURSE_WORKFLOW_SECRET` (existing, unchanged) verifies every
Workflow name. Neither is scoped further (e.g. per-event-type or
per-workflow-name secrets) — this matches how Discourse itself models
it: one webhook definition in Discourse's admin UI has one secret and
delivers however many event types you select to it; a Workflow's HTTP
action step computes one HMAC with whatever secret its Code step uses.

## Risks / Trade-offs

- **[Confirmed during apply]** `user_badge_granted`/`user_badge_revoked`
  payloads only carry a numeric user ID, never a username — the exact
  risk flagged during proposal. Resolved per explicit direction (see
  the badge-event decision above) rather than requiring the
  admin-level Discourse API access this project previously avoided:
  these two triggers fail loudly (not silently) until Discourse adds
  the field, instead of being descoped entirely.
- **[Risk]** Removing replay-window protection is a real reduction in
  defense-in-depth against a captured-and-replayed valid request (the
  signature alone no longer has a staleness backstop). →
  **Mitigation**: accepted per proposal.md's explicit rationale —
  every action is idempotent, so a replay produces no unwanted side
  effect; the signature check still prevents a *forged* request.
- **[Risk]** This is a breaking schema change to both `config.yaml` and
  `rules.yaml` for any existing deployment. → **Mitigation**: this is
  pre-production (MVP), and the proposal's migration notes (and the
  REMOVED requirements' per-requirement **Migration** text) give the
  exact config/rules.yaml edits needed; no deployment has to run both
  schemas simultaneously.

## Migration Plan

1. Deploy this change's code (new trigger types registered, old one
   removed).
2. Update the live `config.yaml`: remove `discourse.webhook.*` entirely.
3. Update the live `rules.yaml`: replace the `discourse_trust_level`
   rule with `{type: workflow, name: "trusted"}` (same action).
4. Set `DISCOURSE_WEBHOOK_SECRET` in the environment (required at
   startup, same fail-fast posture as other required secrets) — even if
   no native webhook is configured yet in Discourse, since the route
   handler always verifies against it for any `X-Discourse-Event`
   request.
5. Remove `DISCOURSE_REPLAY_WINDOW_SECONDS` from the environment
   (no longer read).
6. No Discourse-side reconfiguration needed for the existing "trusted"
   Workflow to keep working. Configuring a native webhook for
   `user_promoted`/badge events in Discourse's admin UI is optional and
   independent — can happen whenever the team is ready to use it.
