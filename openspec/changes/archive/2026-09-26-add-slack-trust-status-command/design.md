## Context

`/trust` and `/revoke` (both implemented — see the archived
`add-slack-trust-grant` and `add-slack-revoke-command` changes) share a
pattern: a Slack command builds a `TriggerEvent`, the rules engine
evaluates and executes matching rules, and outcomes get formatted back to
Slack. `/trust-status` explicitly does not fit that pattern (see
proposal.md - Why): it never touches the rules engine, and it reads from
three independent sources instead of mutating one. This document covers
the pieces that pattern doesn't answer: the Discourse client's shape (the
first real use of that integration), how a read spanning three sources
handles a partial failure, and where the read-only channel check lives
given there's no `TriggerEvent` to gate.

## Goals / Non-Goals

**Goals:**
- Define `DiscourseClient`'s shape and error-handling model — the first
  code in this repo to actually call the Discourse API.
- Define the audit log's first read function.
- Define how `/trust-status` enforces its authorization checks without a
  `TriggerEvent`, and how it aggregates three data sources into one
  response, including the partial-failure and unknown-user behavior
  already confirmed with the user in proposal.md.

**Non-Goals:**
- The Discourse *webhook* trigger (`src/triggers/discourse.py`,
  `src/api/webhooks.py`) — separate future change, different code path
  (inbound webhook, not this outbound read API).
- Anything about `/trust` or `/revoke`'s existing behavior.
- What the system must do externally — fixed by
  `specs/slack-trust-status-command/spec.md`; this document is
  implementation approach only.

## Decisions

### DiscourseClient mirrors KeycloakClient's client-singleton pattern
Add `src/integrations/discourse.py: DiscourseClient` wrapping
`pydiscourse.DiscourseClient`, with the same `build_client()` /
`set_client()` / `get_client()` module-level singleton functions
`src/integrations/keycloak.py` already has. `src/main.py` constructs and
installs it at startup the same way it does the Keycloak client, using
`config.discourse.base_url` and the `DISCOURSE_API_KEY` /
`DISCOURSE_API_USERNAME` env vars. Alternative considered: a bare module
function instead of a client class. Rejected — the singleton pattern is
already established and tests already know how to inject a fake client
via `set_client()`; a different shape for the second integration would be
inconsistent for no benefit.

### No retry-on-connectivity-failure for the Discourse read
Unlike `KeycloakClient`, `DiscourseClient.get_trust_level()` makes a
single attempt and lets any exception (a connectivity error from
`requests`, or a `pydiscourse.exceptions.DiscourseError` for a non-2xx
response, e.g. the user not existing on Discourse) propagate immediately.
Keycloak's retry-once-then-fail exists because a spurious failure there
could otherwise abort a real grant/revoke; there's no equivalent
"don't-spuriously-fail-a-mutation" concern here, since `/trust-status`
degrades gracefully by design (see below) rather than aborting. Retrying
would only add latency to every `/trust-status` call for no behavioral
benefit. `pydiscourse`'s 404-for-unknown-user and any connectivity error
are both just "this section is unavailable" from the caller's
perspective — no need to distinguish them the way Keycloak's
`UserNotFoundError` vs `KeycloakConnectionError` are distinguished (see
below, that distinction matters for Keycloak specifically because it
gates the whole response).

### New audit read function: `src/audit/db.py: get_recent_events()`
Add `get_recent_events(conn, openmrs_id, *, limit=5) -> list[sqlite3.Row]`
(or equivalent), a single `SELECT ... WHERE openmrs_id = ? ORDER BY id
DESC LIMIT ?`. It lives in `src/audit/db.py` alongside `record_event()`
rather than a new module — it's the same table, same connection, same
"only what this module needs" scope `src/audit/db.py` already has.
`/trust-status` results are **not** written back to `audit_log`: the
table's purpose (per the `audit-log` capability) is a record of
access-provisioning actions, and a status lookup changes nothing — logging
it there would conflate "an action was attempted" with "someone looked
something up." (Nothing prevents adding general request logging later;
that's a different, out-of-scope concern from this append-only table.)

### Channel/signature check without a TriggerEvent
`/trust`/`/revoke`'s channel check lives in `build_trust_event()` /
`build_revoke_event()` (`src/triggers/slack.py`) because its job is
partly to construct the `TriggerEvent` the engine needs. `/trust-status`
has no `TriggerEvent` to construct — per its spec, it must never reach the
rules engine — so adding a `build_trust_status_event()` there would misuse
that module for a return value nothing consumes. Instead, `_handle_trust_status()`
(in `src/integrations/slack.py`, alongside `_handle_trust`/`_handle_revoke`)
does the channel-id comparison inline, then proceeds directly to the
read/aggregate path. Alternative considered: still route through
`src/triggers/slack.py` for consistency. Rejected — consistency with a
pattern whose entire purpose (feeding the engine) doesn't apply here would
be consistency for its own sake, at the cost of a misleading module
boundary.

### Keycloak "not found" gates the whole response; other failures degrade per-section
`KeycloakClient.get_user_groups()` already raises `UserNotFoundError` when
the OpenMRS ID doesn't exist, and `KeycloakConnectionError` (via the
existing retry-once wrapper) on connectivity failure — reused as-is, no
Keycloak client changes needed. `_handle_trust_status()` treats these
differently:
- `UserNotFoundError` → the whole command responds "OpenMRS ID not found"
  and skips the Discourse/audit lookups entirely. Keycloak is the SSO
  identity source of truth (§3 of the spec: Discourse username is always
  identical to the Keycloak username), so a Keycloak-unknown ID isn't a
  real community member to report partial status for.
- Any other exception (`KeycloakConnectionError`, or an unexpected error)
  → the Keycloak-groups section of the response is marked unavailable,
  and the Discourse and audit-log lookups still proceed independently —
  per the confirmed partial-data behavior.

The Discourse and audit-log lookups are each wrapped in their own
try/except in `_handle_trust_status()`, independent of each other and of
the Keycloak outcome, so a failure in one never prevents the other two
from being reported.

## Risks / Trade-offs

- **[Risk]** Showing partial data on a backend failure could mask a real
  outage from whoever's reading the Slack response (they might not notice
  "unavailable" in a wall of text). → **Mitigation:** each unavailable
  section names *why* (e.g. "(connection error)"), and this is a
  human-in-the-loop, low-volume command (issued from a private channel by
  vetted members) rather than an automated consumer that would need to
  react programmatically to a degraded response.
- **[Risk]** Treating a Discourse 404 (user genuinely has no Discourse
  account) the same as a Discourse outage in the UI text could be
  ambiguous. → **Mitigation:** acceptable per the confirmed decision to
  keep Discourse error handling simple (no retry, no error-type
  distinction) — this is a display nicety, not a behavior correctness
  issue, and can be refined later if it proves confusing in practice.

## Migration Plan

Purely additive — no existing behavior changes, no data migration, no
new config keys (the Discourse env vars were already documented,
just previously unused). Local dev/testing follows the same pattern as
`/trust`/`/revoke`: set `DISCOURSE_API_KEY`/`DISCOURSE_API_USERNAME` in
`.env` pointing at a real or test Discourse instance.
