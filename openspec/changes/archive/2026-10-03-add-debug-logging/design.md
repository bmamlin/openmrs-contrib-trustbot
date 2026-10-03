# Design

## Context

`src/logging_setup.py` already configures a JSON-formatted root logger
and `set_log_level()`/`POST /admin/log-level` already changes it at
runtime (see the archived `add-admin-log-level-api` change). Four
modules already have a `logger = logging.getLogger(__name__)` and log at
WARNING (`src/api/webhooks.py`, `src/api/admin.py`,
`src/integrations/slack.py`, and implicitly the rate-limit/dry-run work).
Nothing logs at DEBUG. See proposal.md for why, and for the
already-confirmed decision on raw-vs-curated body dumps.

`src/engine/models.py: TriggerEvent` (`type`, `name`, `openmrs_id`,
`source`, `payload: dict`) is constructed by each trigger's
`build_event()` (`src/triggers/discourse_webhook.py`,
`discourse_workflow.py`, `src/triggers/slack.py`) specifically to hold
only the fields that trigger's matcher/action needs — it is already the
curated object proposal.md's decision calls for logging.

## Goals / Non-Goals

**Goals:**
- One generic DEBUG trace point per concern (request received, event
  evaluated, action executed), not one per trigger/action module.
- A single, reusable redaction mechanism so "forgot to redact" isn't
  possible at a new call site without actively bypassing the helper.
- DEBUG logging that works today, with the existing admin endpoint and
  `LOG_LEVEL` env var — no new configuration surface.

**Non-Goals:**
- Raw Discourse webhook payload dumps — explicitly rejected per
  proposal.md's confirmed decision.
- A generic/pluggable redaction *policy* (e.g. configurable via
  `config.yaml`) — the denylist is small, known, and hardcoded; this
  isn't a feature surface that needs to be user-configurable.
- Request/response body logging for outbound calls to Keycloak or
  Discourse's `/trust-status` read path — out of scope; only the
  connectivity-retry signal is added for Keycloak (proposal.md), and
  nothing changes for the Discourse read client.

## Decisions

### `TriggerEvent` is the payload-dump unit, logged once in `evaluator.py`
Rather than adding a log call inside every `build_event()` (one per
trigger type, growing over time), `evaluator.evaluate(rule_set, event)`
logs the event once, generically, the moment it receives one:
`logger.debug("evaluating event: type=%s name=%s openmrs_id=%s payload=%s", ...)`.
Every trigger type gets this for free, including ones added later.
Alternative considered: log inside each `build_event()`, closer to where
the raw payload was available for comparison. Rejected — that's the
"one call site per trigger type" pattern this proposal is explicitly
trying to avoid, and `evaluate()` already receives every event
regardless of source, making it the natural single chokepoint.

### Headers are logged in full (minus `Authorization`); bodies are not
`src/logging_setup.py` gains:
```python
REDACTED_HEADER_NAMES = {"authorization"}
REDACTED_SLACK_BODY_FIELDS = {"token"}

def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k: ("[REDACTED]" if k.lower() in REDACTED_HEADER_NAMES else v) for k, v in headers.items()}

def redact_slack_body(body: Mapping[str, Any]) -> dict[str, Any]:
    return {k: ("[REDACTED]" if k in REDACTED_SLACK_BODY_FIELDS else v) for k, v in body.items()}
```
Two small functions rather than one generic `redact_mapping(data,
denylist)` — the denylists differ in both name-casing rules (headers
are case-insensitive; Slack body keys are not) and in what "the body"
even means per endpoint (Discourse's raw body is deliberately *not*
logged at all, per the Non-Goal above, so there's no third
`redact_discourse_body()` to add symmetry pressure). Each call site logs
headers via `redact_headers(dict(request.headers))`; Slack's command
body via `redact_slack_body(command)`.

### The Discourse webhook route logs headers before parsing, the event after
`src/api/webhooks.py`'s route handler logs redacted headers immediately
(before signature verification) — this is what would have caught the
`X-Discourse-Event` vs. `X-Discourse-Event-Type` mixup from
`restructure-discourse-triggers`, since the mismatch was visible in
headers alone. It does not log the raw body at all (per the Non-Goal);
the curated view comes later, for free, when the resulting
`TriggerEvent` reaches `evaluator.evaluate()`.

### Slack's global middleware logs before the rate limiter, not inside each handler
The existing `app.use()` middleware (`src/integrations/slack.py`,
added for rate limiting) is extended to log redacted headers and the
redacted command body first, before the rate-limit check — so a
rate-limited command is just as visible as an allowed one, and every
one of `/trust`/`/revoke`/`/trust-status` is covered by one log call
instead of three. `request`/`req` is available to slack-bolt middleware
via the same kwargs-injection mechanism already confirmed for `body`
(see `add-rate-limiting` design.md's investigation into `Args`).

### `execute_rule()` logs the action and outcome, not each action module
Mirroring the `evaluate()` decision: `execute_rule()` logs
`logger.debug("executing action: rule=%r type=%s", rule.name,
action.type)` before calling the executor, and `logger.debug("action
result: rule=%r type=%s status=%s detail=%s", ...)` after — covering
`keycloak_add_groups`/`keycloak_remove_groups` today and any future
action type for free, without `src/actions/keycloak.py` needing a
logger at all.

### Keycloak retries log inline, where the retry decision is made
`src/integrations/keycloak.py: KeycloakClient._call_with_retry()` gets
its own module logger and logs `logger.debug("retrying %s after
connection error (attempt %d/%d)", fn.__name__, attempt, attempts)` in
the `except KeycloakConnectionError` branch, right before `time.sleep()`.
This is the one place in this proposal where a per-module log call is
correct rather than a chokepoint — retries are specific to this one
client's connectivity handling, there's no generic "retry" concept
elsewhere in the engine to centralize into.

## Risks / Trade-offs

- **[Risk]** Logging `TriggerEvent.payload` at DEBUG is only as safe as
  each `build_event()`'s existing choice of what to put in `payload` —
  if a future trigger type's author puts something sensitive there,
  this proposal's redaction helpers won't catch it (they only cover
  headers and the Slack body's `token` field). → **Mitigation**:
  documented directly in the `debug-logging` spec and in
  `TriggerEvent`'s own docstring once this lands — `payload` is already
  understood as "the curated, already-decided-safe subset," and this is
  the same trust boundary the audit log already relies on (every
  `TriggerEvent.payload` already gets written to `action_detail` /
  `audit_log` regardless of log level today).
- **[Risk]** DEBUG at this verbosity (every request, every evaluation,
  every action) is noisy in production if left on. → **Mitigation**:
  this is exactly what the existing admin endpoint is for — DEBUG is
  meant to be toggled on for the duration of an investigation, not run
  continuously; no change needed here, just the existing runtime
  toggle doing its job for the first time.

## Migration Plan

Purely additive — no existing behavior changes at `INFO` or above. Any
deployment can start seeing DEBUG output immediately by calling the
existing `POST /admin/log-level?level=DEBUG` or setting `LOG_LEVEL=DEBUG`;
no config schema changes.
