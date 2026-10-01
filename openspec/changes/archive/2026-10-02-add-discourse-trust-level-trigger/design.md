## Context

`src/api/webhooks.py` is a stub `POST /webhook/discourse` route, already
mounted in `src/main.py` since the original scaffolding, that has never
been implemented because the real webhook mechanism was unknown until
now (see proposal.md - Why for the research path that got us here). Unlike
`/trust`/`/revoke`/`/trust-status`, there's no framework here doing
signature verification or request-context plumbing for us the way
slack-bolt does for the Slack commands — this document covers that gap:
how the raw HMAC verification works, how the handler reaches the audit
connection and rules engine without an `App`-like container object, and
the replay-window/workflow-name checks that are new to this trigger.

## Goals / Non-Goals

**Goals:**
- Define the exact verification order and HTTP status codes for the
  webhook endpoint.
- Define how `src/api/webhooks.py`'s route handler gets access to the
  shared secret, replay window, expected workflow name, and the audit
  connection, given it isn't bundled into a stateful app object like
  `slack-bolt`'s `App`.
- Define the `discourse_trust_level` `TriggerEvent`'s shape, in
  particular what `source` (the audit log's `trigger_src` column) should
  be for a webhook-originated event, since there's no Slack-style human
  issuer here.

**Non-Goals:**
- Rate limiting on this endpoint — deferred, as in every prior change.
- Anything about `/trust-status`'s existing `DiscourseClient`
  (`src/integrations/discourse.py`) — untouched by this change.
- What the system must do externally — fixed by
  `specs/discourse-trust-level-trigger/spec.md`; this document is
  implementation approach only.

## Decisions

### Factory function + context object, mirroring `create_slack_app()`
`src/api/webhooks.py` exposes `create_webhooks_router(*, webhook_secret:
str, replay_window_seconds: int, workflow_name: str, audit_conn:
sqlite3.Connection) -> APIRouter`, replacing the current module-level
`router = APIRouter()`. Internally it builds a small `WebhookContext`
dataclass (mirroring `src/integrations/slack.py`'s `SlackContext`) closed
over by the route handler. `src/main.py` calls this factory once at
startup — the same shape as `create_slack_app()` — instead of importing a
bare `router` attribute. Alternative considered: reach into
`request.app.state` directly inside the handler (mirroring how
`audit_conn`/`keycloak_client` are stored there today). Rejected for this
case — the factory+context shape is already this codebase's established
pattern for "a handler needs more than the raw payload" (see
`SlackContext`), and it keeps the handler unit-testable the same way
`_handle_trust()` is: construct a context, call the function directly,
assert on the response, no FastAPI app or `request.app.state` needed in
the test.

### Verification order and status codes
In this exact order, matching `specs/discourse-trust-level-trigger/spec.md`:
1. Read the raw request body (`await request.body()`) — never
   re-serialize a parsed payload for signature checking, since
   re-serialization can change byte-for-byte content (whitespace, key
   order) and silently break a valid signature.
2. Verify `X-Discourse-Workflow-Secret` (`sha256=<hex>` — strip the
   prefix, compute HMAC-SHA256 of the raw body with `webhook_secret`, and
   compare using `hmac.compare_digest` for constant-time comparison). On
   failure: HTTP 403, matching the original (still-valid, unmodified)
   requirement in `overview.md` §5.2 for Discourse webhook signature
   failures specifically.
3. Compare `X-Discourse-Workflow` against the configured `workflow_name`.
   On mismatch: HTTP 400.
4. Parse the body as JSON. On failure, or a missing/wrong-typed
   `username`, `new_trust_level`, or `timestamp` field: HTTP 400.
5. Parse `timestamp` with `datetime.fromisoformat()` (handles the `Z`
   suffix natively on Python 3.11+) and check
   `abs(now_utc - event_time) <= replay_window_seconds`. Outside the
   window (past *or* future — guards against both a replayed old capture
   and a clock-skewed/forged future timestamp): HTTP 400.
6. Build a `TriggerEvent`, call `load_rules()` + `evaluate()` +
   `execute_rule()` for each matched rule (exactly as the Slack handlers
   already do), then respond HTTP 200.

Steps 2-3 only need the raw body and headers — no JSON parsing yet. This
keeps malformed-but-correctly-signed-and-routed payloads cleanly separate
from auth/routing failures, and avoids ever parsing JSON from a request
that hasn't even passed signature verification.

### `TriggerEvent` shape and audit `trigger_src`
```python
TriggerEvent(
    type="discourse_trust_level",
    openmrs_id=payload["username"],       # already resolved by Discourse; no lookup needed
    source=config.discourse.base_url,     # e.g. "https://talk.openmrs.org"
    payload={
        "old_trust_level": payload["old_trust_level"],
        "new_trust_level": payload["new_trust_level"],
    },
)
```
There's no human issuer the way Slack commands have an issuing username —
this is an automated system event. `overview.md`'s `audit_log` schema
comment already anticipates this: `trigger_src` is documented as "e.g.
Slack username, **Discourse webhook URL**". Using the configured Discourse
instance URL as `source` matches that existing hint directly, needs no
new config, and is simpler than trying to thread a per-request value
through (the Discourse Workflow's HTTP action doesn't send an
`X-Discourse-Instance` header the way native Discourse webhooks do, so
there's nothing more specific available per-request anyway).

### `discourse_trust_level` trigger matcher
`src/triggers/discourse.py: matches(trigger, event)` becomes a direct
port of the semantics already written in `config-schema.md` and already
present in `config/rules.example.yaml`: `trigger.type ==
"discourse_trust_level" and event.type == "discourse_trust_level" and
event.payload["new_trust_level"] >= trigger.threshold`. No "crossing-only"
logic — this was already decided in that doc before this change existed,
and `keycloak_add_groups`'s existing idempotency already makes repeated
matches harmless.

### `DISCOURSE_REPLAY_WINDOW_SECONDS` override, resolved in `main.py`
This env var has been documented in `.env.example` since the original
scaffolding but never actually read anywhere (nothing used
`replay_window_seconds` until now). Resolve it the same way
`src/main.py` already resolves everything else — read directly from
`os.environ` at startup, falling back to the parsed config value:
`int(os.environ.get("DISCOURSE_REPLAY_WINDOW_SECONDS",
config.discourse.webhook.replay_window_seconds))`. Keeping this in
`main.py` (not inside `src/config.py`) is consistent with
`src/config.py`'s own stated design — it intentionally stays pure YAML
parsing, with env var reads left to the callers that need them.

## Risks / Trade-offs

- **[Risk]** `hmac.compare_digest` requires comparing like-typed values
  (both `bytes`, or both `str`) — a careless `bytes`/`str` mismatch would
  raise instead of safely returning `False`. → **Mitigation**: decode the
  header's hex digest consistently (e.g. compare the two hex *strings*
  directly with `compare_digest`, rather than mixing in raw bytes), and
  cover this explicitly in a unit test.
- **[Risk]** A clock-skewed or misconfigured server clock on either side
  could cause legitimate requests to be rejected as "stale" even though
  nothing is actually wrong. → **Mitigation**: the default 300-second
  window is generous; if this proves too strict in practice, widening it
  is a `config.yaml` change, not a code change.

## Migration Plan

Purely additive — no existing behavior changes. Deploying this requires
the OpenMRS ITSM team's Discourse Workflow to already be configured
(confirmed live-tested during this change's research) and the
`DISCOURSE_WORKFLOW_SECRET` env var set to match the secret used in the
Workflow's Code step. `config.yaml` needs the new
`discourse.webhook.workflow_name` value set to match the Workflow's
actual configured name on `talk.openmrs.org` before this goes live, or
every request will be rejected at the workflow-name-validation step.
