# Tasks

## 1. Redaction helpers

- [x] 1.1 In `src/logging_setup.py`, add `REDACTED_HEADER_NAMES =
      {"authorization"}`, `REDACTED_SLACK_BODY_FIELDS = {"token"}`,
      `redact_headers(headers: Mapping[str, str]) -> dict[str, str]`
      (case-insensitive key match), and `redact_slack_body(body:
      Mapping[str, Any]) -> dict[str, Any]`. Verify
      `tests/unit/test_logging_setup.py` gains cases: `redact_headers`
      replaces an `Authorization` value (any case) with `"[REDACTED]"`
      and leaves other headers untouched; `redact_slack_body` replaces
      a `token` field's value and leaves other fields untouched;
      neither function mutates its input mapping.

## 2. Rules engine chokepoints

- [x] 2.1 In `src/engine/evaluator.py`, add a module logger. In
      `evaluate()`, log at DEBUG the event's `type`, `name`, and
      `openmrs_id`, and after computing matches, log the matched rules'
      names (or that none matched). In `execute_rule()`, log at DEBUG
      before each executor call (rule name, action type) and after
      (rule name, action type, result status and detail). Verify
      `tests/unit/engine/test_evaluator.py` gains cases (via `caplog`):
      `evaluate()` logs the event and matched rule names when one or
      more rules match, and logs that none matched when none do;
      `execute_rule()` logs both the attempt and the result for a
      successful action, and for a failing one (the existing
      "executor raises" test case).
- [x] 2.2 In `src/engine/loader.py`, add a module logger. In
      `load_rules()`, log at DEBUG the resolved path and the number of
      rules loaded. Verify `tests/unit/engine/test_loader.py` gains a
      case asserting this via `caplog`.

## 3. Discourse webhook route

- [x] 3.1 In `src/api/webhooks.py`, log redacted headers
      (`logging_setup.redact_headers`) at DEBUG as the first step in
      `discourse_webhook_route()` — before the rate-limit check, so a
      rate-limited or signature-rejected request is just as visible as
      an accepted one. Do not log the raw request body (per
      design.md's Non-Goal — the curated `TriggerEvent` is logged
      later, generically, by task 2.1). Verify
      `tests/unit/api/test_webhooks.py` gains cases (via `caplog`):
      headers are logged at DEBUG for a request that is ultimately
      accepted, for one rejected by signature verification, and for
      one rejected by rate limiting; the logged headers never contain
      an `Authorization` entry's real value (this route doesn't send
      one, but the assertion documents the guarantee); the raw body is
      never present in any DEBUG record for this route.

## 4. Admin endpoint

- [x] 4.1 In `src/api/admin.py`, log redacted headers at DEBUG as the
      first step in the route handler (before the auth check). Add a
      DEBUG log for a successful level change (today only the
      rejection path logs, at WARNING). Verify
      `tests/unit/api/test_admin.py` gains cases (via `caplog`):
      headers are logged at DEBUG with the `Authorization` header's
      value replaced by `"[REDACTED]"` (not merely absent — assert the
      literal presented bearer token string never appears anywhere in
      the captured records); a successful level change logs the new
      level at DEBUG.

## 5. Slack commands

- [x] 5.1 In `src/integrations/slack.py`'s global `app.use()`
      middleware, add `request` (or `req`) as a parameter (available
      via slack-bolt's kwargs injection, confirmed in design.md) and
      log redacted headers plus the redacted command body
      (`logging_setup.redact_slack_body`) at DEBUG as the first step,
      before the rate-limit check. Verify `tests/unit/integrations/test_slack.py`
      gains a case (invoking the registered middleware function
      directly, per the existing `test_slack_rate_limiting.py` pattern)
      asserting: the command body is logged at DEBUG with its `token`
      field (if present) replaced by `"[REDACTED]"`, for both an
      allowed and a rate-limited command.

## 6. Keycloak connectivity

- [x] 6.1 In `src/integrations/keycloak.py`, add a module logger. In
      `KeycloakClient._call_with_retry()`, log at DEBUG when a
      `KeycloakConnectionError` triggers a retry (function name,
      attempt number, max attempts). Verify
      `tests/unit/integrations/test_keycloak.py` gains a case (via
      `caplog`, extending the existing
      `test_add_user_to_groups_retries_once_on_connection_error_then_succeeds`-style
      fixture) asserting a DEBUG record is emitted for the retry.

## 7. Docs

- [x] 7.1 Update `openspec/specs/overview.md` §5.5's "DEBUG mode must
      never log secrets..." bullet to reflect that this is now
      implemented (not just stated), and note the curated-vs-raw
      payload decision from design.md inline or via a pointer to the
      archived change.
- [x] 7.2 Update `CLAUDE.md`'s "Current state" note: DEBUG logging is
      implemented (request headers, rule-evaluation flow, action
      outcomes, Keycloak retries), with the redaction guarantees
      design.md documents. Update `README.md` with a short "Use DEBUG
      logging" manual-testing subsection (enable via the admin endpoint
      or `LOG_LEVEL=DEBUG`, trigger a command, observe the trace).

## 8. Full verification

- [x] 8.1 Run `pytest` and confirm every unit, integration, and
      security test — old and new — passes; run `python -m py_compile`
      over all changed files under `src/`; run `openspec validate
      --strict` against this change.
      DONE: 187/187 tests pass (5 consecutive full-suite runs, no
      flakiness), `py_compile` clean, `openspec validate --strict`
      valid.
