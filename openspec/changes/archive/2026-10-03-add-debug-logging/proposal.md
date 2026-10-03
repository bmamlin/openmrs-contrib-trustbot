# Proposal

## Why

The service already supports toggling between `INFO` and `DEBUG` at
runtime (`POST /admin/log-level`), and `overview.md` §5.5 requires DEBUG
mode to exist for exactly this reason — but there is not a single
`logger.debug()` call anywhere in `src/`. Flipping to DEBUG today changes
nothing. An operator trying to diagnose a stuck rule, a signature
mismatch, or why an action didn't fire has no additional visibility to
reach for.

## What Changes

- Add DEBUG-level logging for three things, everywhere they occur:
  1. **Every incoming POST** (`/webhook/discourse`, `/slack/commands`,
     `/admin/log-level`) — request headers and a curated view of the
     body, logged before any authorization decision, so a rejected
     request is just as visible as an accepted one.
  2. **The flow of the application** — which event was evaluated against
     `rules.yaml`, which rules matched, and which didn't.
  3. **Every action taken** — which action ran for which rule, and its
     outcome (status + detail), for every trigger/action type uniformly.
- Add a shared redaction helper (`src/logging_setup.py`) so "log the
  request" can never accidentally include a credential: the
  `Authorization` header (the admin endpoint's bearer token) and Slack's
  deprecated `token` body field are excluded from any DEBUG dump, by
  construction, not by remembering to do it at each call site.
- **Decision** (confirmed with the user — see design.md): body dumps are
  *curated*, not raw. `TriggerEvent` (type, name, openmrs_id, and the
  specific normalized fields each trigger's `build_event()` already
  chooses to extract) is itself the right thing to log — it's already
  exactly the curated subset this service cares about, by construction.
  Raw Discourse webhook bodies (e.g. `user_promoted`'s full serialized
  user — profile fields, notification settings, group memberships) are
  **not** dumped wholesale; this keeps `overview.md` §5.5's existing
  "DEBUG must never log raw webhook payloads containing sensitive data"
  requirement intact instead of relaxing it. Headers, by contrast, are
  logged in full (minus `Authorization`) — they're low-risk and exactly
  what would have caught a recent real bug (confusing
  `X-Discourse-Event` with `X-Discourse-Event-Type`) that a payload dump
  alone would not have shown.
- Add DEBUG logging for Keycloak connectivity retries
  (`src/integrations/keycloak.py`), since a flaky/slow Keycloak is a
  real, previously-invisible failure mode.

## Capabilities

### New Capabilities
- `debug-logging`: what gets logged at DEBUG level and the redaction
  guarantees around it — the behavior contract `overview.md` §5.5
  already describes but nothing currently implements.

### Modified Capabilities
(none — every existing capability's actual behavior is unchanged; this
only adds an observability side-channel. `admin-log-level-api`'s
contract, for example, still does exactly what it did before; it simply
becomes meaningfully different to *use* once switched to DEBUG.)

## Impact

- `src/logging_setup.py`: add `redact_headers()` and
  `redact_slack_body()` (or one generic `redact_mapping()` with a
  per-context denylist) helpers.
- `src/engine/evaluator.py`: `evaluate()` logs the event and the matched
  rule names at DEBUG; `execute_rule()` logs each action attempted and
  its outcome at DEBUG — this is the single generic chokepoint that
  covers every trigger/action type without touching
  `src/triggers/`/`src/actions/` individually.
- `src/engine/loader.py`: `load_rules()` logs the resolved path and rule
  count at DEBUG.
- `src/api/webhooks.py`: logs redacted headers and which branch
  (webhook/workflow/neither) was taken, before signature verification.
- `src/api/admin.py`: logs redacted headers; logs a successful level
  change at DEBUG (today only the rejection path logs, at WARNING).
- `src/integrations/slack.py`: the existing global `app.use()` middleware
  gains a DEBUG dump of redacted headers and the command body (minus
  `token`), running before the rate-limit check so every command is
  visible regardless of outcome.
- `src/integrations/keycloak.py`: `_call_with_retry()` logs each retry
  attempt at DEBUG.
- Test collateral: new `caplog`-based DEBUG assertions alongside the
  existing WARNING ones, across `tests/unit/` and `tests/integration/`.
