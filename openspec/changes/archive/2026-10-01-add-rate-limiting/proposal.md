# Proposal

## Why

Both HTTP-reachable endpoints — `POST /webhook/discourse` and
`POST /slack/commands` — are now live in production with no protection
against a flood of requests: a misconfigured or compromised Discourse
instance could hammer the webhook endpoint, and a Slack channel member
could spam `/trust`/`/revoke`/`/trust-status` in rapid succession. The
original spec (`overview.md` §6.4, §6.6) already requires rate limiting on
both, and `config.yaml`'s `rate_limiting` block has existed, fully parsed
(`src/config.py: RateLimitingConfig`), since the very first scaffolding —
it has simply never had a consumer.

## What Changes

- Rate limit `POST /webhook/discourse` per source IP
  (`rate_limiting.discourse_webhook`): requests exceeding the configured
  threshold get HTTP 429, before any signature/payload processing.
- Rate limit `POST /slack/commands` per issuing Slack user
  (`rate_limiting.slack_commands`), shared across all three commands
  (`/trust`, `/revoke`, `/trust-status`) rather than three separate pools
  — the config schema has a single `slack_commands` block, not one per
  command. A rate-limited user gets a visible Slack message (unlike the
  silent channel-restriction rejection already in place) explaining
  they're rate limited.
- Add a minimal, real logging setup (`logging.getLogger`-based, JSON
  output to stdout, honoring `LOG_LEVEL` at startup — documented in
  `.env.example`/`config-schema.md` since scaffolding, never read by any
  code until now) — just enough to emit WARNING-level log lines for rate
  limit violations and for the authorization failures this change's own
  code already handles (Discourse signature/workflow-name rejections;
  Slack's silent channel-restriction rejections), per `overview.md` §6.6's
  combined requirement ("Authorization failures and rate limit violations
  logged at WARNING level or above"). This does **not** cover Slack's own
  signature verification (handled entirely inside `slack-bolt`, before our
  code runs — we have no hook to log that without patching the library),
  and does **not** build the runtime log-level-changing admin API
  (`overview.md` §5.5) — that stays a separate, deferred change.
- **Noted discrepancy, not silently resolved:** `overview.md` §6.4 says
  rate limit thresholds are "configurable via environment variables," but
  the actual established schema (`config-schema.md`, what every prior
  change has built against) has no such env vars — only `config.yaml`
  fields. This change follows `config-schema.md` (no new env vars for
  thresholds); `overview.md`'s line is superseded in practice.

Out of scope: the admin log-level API itself, full JSON-structured
logging for every code path in the app, dry-run/simulation mode, and any
change to `/trust`/`/revoke`/`/trust-status`/the Discourse trigger's
existing business logic beyond adding the rate-limit check and (where our
own code handles the rejection) a log line.

## Capabilities

### New Capabilities
- `discourse-webhook-rate-limiting`: per-source-IP request throttling on
  `POST /webhook/discourse`, including the WARNING-level log line on
  violation.
- `slack-command-rate-limiting`: per-Slack-user request throttling shared
  across `/trust`, `/revoke`, and `/trust-status`, including the visible
  Slack response and the WARNING-level log line on violation.

### Modified Capabilities
- `discourse-trust-level-trigger`: adds a requirement that signature and
  workflow-name rejections are logged at WARNING level (new observable
  side effect on existing, unchanged rejection behavior).
- `slack-trust-command`: adds a requirement that the silent
  channel-restriction rejection is also logged at WARNING level.
- `slack-revoke-command`: same addition as `slack-trust-command`, for its
  own channel-restriction rejection.
- `slack-trust-status-command`: same addition, for its channel-restriction
  rejection.

## Impact

- New module under `src/` for the in-memory rate limiter(s) (exact shape
  decided in `design.md`).
- New minimal logging setup, likely a small `src/logging_setup.py`-style
  module or inline in `src/main.py` (decided in `design.md`), first real
  consumer of `LOG_LEVEL`.
- `src/api/webhooks.py`: rate-limit check added to the verification
  pipeline; signature/workflow-name rejections gain a log call.
- `src/integrations/slack.py`: a `slack-bolt` global middleware added for
  per-user rate limiting; existing channel-restriction rejection paths
  gain a log call.
- `src/main.py`: constructs the rate limiter(s) and logging setup at
  startup, using `config.rate_limiting.discourse_webhook` /
  `config.rate_limiting.slack_commands`.
- No `rules.yaml` or `config.yaml` schema changes — `rate_limiting` has
  been fully defined since scaffolding.
- No new environment variables.
