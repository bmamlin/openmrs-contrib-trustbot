# Tasks

## 1. Rate limiter core

- [x] 1.1 Implement `src/ratelimit.py: RateLimiter` (constructed with
      `max_requests`, `window_seconds`; `is_allowed(key: str) -> bool`
      using a lock-guarded fixed-window counter per key, per design.md);
      verify `tests/unit/test_ratelimit.py` (new) covers: requests under
      the limit are allowed, the request that exceeds the limit is
      rejected, the counter resets once `window_seconds` has elapsed
      (use a short window and a monkeypatched/fake clock or
      `time.sleep` for the reset case), and concurrent calls from
      multiple threads never allow more than `max_requests` through
      (a real `threading.Thread`-based test, mirroring
      `tests/unit/audit/test_db.py`'s cross-thread regression test
      style).

## 2. Minimal logging setup

- [x] 2.1 Implement a JSON `logging.Formatter` subclass and a
      `configure_logging()` function (in `src/main.py` or a new
      `src/logging_setup.py` if it grows past a few lines) that calls
      `logging.basicConfig` with that formatter, setting the level from
      `LOG_LEVEL` (env var) falling back to `config.logging.level` (same
      override pattern as `DISCOURSE_REPLAY_WINDOW_SECONDS`); verify
      `tests/unit/test_logging_setup.py` (new, or alongside
      `tests/unit/test_main.py` if inlined) covers: a log record emitted
      after configuration produces valid JSON on stdout/a captured
      stream with the expected keys, and `LOG_LEVEL=WARNING` suppresses
      an INFO-level log call while `LOG_LEVEL=DEBUG` does not.

## 3. Discourse webhook: rate limiting + logging

- [x] 3.1 In `src/api/webhooks.py`, add the rate-limit check as the first
      step in the route handler (before signature verification), keyed
      by the source IP (first address in `X-Forwarded-For` if present,
      else `request.client.host`, per design.md); exceeding the limit
      returns HTTP 429 without reading/verifying the body; verify
      `tests/unit/api/test_webhooks.py` gains cases for: a request within
      the limit proceeds to signature verification as before, a request
      exceeding the limit gets HTTP 429 and never reaches
      `_verify_signature`, and the IP is read from `X-Forwarded-For` when
      present (falling back to the connecting client otherwise).
- [x] 3.2 Add `logging.getLogger(__name__).warning(...)` calls for: the
      new rate-limit rejection (identifying the source IP), the existing
      invalid-signature rejection, and the existing
      unrecognized-workflow-name rejection; verify the same test file
      asserts (via `caplog` or an equivalent capture) that each of these
      three rejection paths emits a WARNING-level log record.

## 4. Slack commands: rate limiting + logging

- [x] 4.1 In `src/integrations/slack.py: create_slack_app()`, register a
      global `app.use(...)` middleware that checks `body["user_id"]`
      against a shared `RateLimiter` (constructed from
      `rate_limiting.slack_commands` and passed into
      `create_slack_app()`); on violation, call `ack(text=...)` with a
      rate-limited message and do not call `next()`; on success, call
      `next()`; verify `tests/unit/integrations/test_slack.py` gains a
      case confirming the registered `App` has a global middleware
      (mirroring how the existing tests assert on registered command
      listeners).
- [x] 4.2 Add `logging.getLogger(__name__).warning(...)` calls for: the
      new rate-limit rejection (identifying the Slack user ID) in the
      middleware, and the existing silent channel-restriction rejection
      in `_handle_trust`, `_handle_revoke`, and `_handle_trust_status`;
      verify `tests/integration/test_slack_trust_flow.py`,
      `test_slack_revoke_flow.py`, and `test_slack_trust_status_flow.py`
      each gain a case asserting their existing
      wrong-channel-silent-rejection scenario now also emits a
      WARNING-level log record, and a new
      `tests/integration/test_slack_rate_limiting.py` covers: commands
      within the limit succeed normally, exceeding the shared limit
      produces the rate-limited `ack()` message and skips rule
      evaluation entirely, and the limit is genuinely shared across
      `/trust`, `/revoke`, and `/trust-status` (mix command types within
      one test and confirm the combined count is what trips the limit).

## 5. FastAPI wiring

- [x] 5.1 In `src/main.py`, call `configure_logging()` at startup (before
      constructing anything else, so early failures are logged too);
      construct the two `RateLimiter` instances from
      `config.rate_limiting.discourse_webhook` /
      `config.rate_limiting.slack_commands`; pass the Discourse one into
      `webhooks.create_webhooks_router(...)` and the Slack one into
      `create_slack_app(...)`; verify `tests/unit/test_main.py` still
      passes and `GET /health` still returns `200`.

## 6. Security-focused tests

- [x] 6.1 Add `tests/security/test_rate_limiting.py`, exercising both
      endpoints through the real app (`src.main`, mirroring the existing
      security test fixtures' pattern): a burst of validly-signed
      Discourse webhook requests beyond the configured limit gets HTTP
      429 for the excess ones, and a burst of validly-signed Slack
      commands beyond the configured limit gets the rate-limited Slack
      message for the excess ones — per the
      `discourse-webhook-rate-limiting` and `slack-command-rate-limiting`
      specs; verify the tests pass under `pytest`.

## 7. Docs

- [x] 7.1 Update `CLAUDE.md`'s "Current state" note to include rate
      limiting and the minimal logging setup among the implemented
      pieces, and remove rate limiting from the list of what remains
      stubbed (the admin log-level API and dry-run mode stay listed as
      remaining); verify by re-reading the file against the actual final
      behavior.

## 8. Full verification

- [x] 8.1 Run `pytest` and confirm every unit, integration, and security
      test — old and new — passes; run `python -m py_compile` over all
      changed files under `src/`.
