## Context

Both HTTP-reachable endpoints have no abuse protection today, and neither
has any logging at all — `logging.getLogger` is called nowhere in `src/`.
This document covers three things the proposal doesn't: the rate limiter
mechanism itself, where it hooks into the Discourse webhook pipeline
(hand-rolled, no framework) versus the Slack command dispatch (`slack-bolt`
middleware, confirmed to exist and fit this exact use case), and the
shape of the minimal logging setup both rely on.

## Goals / Non-Goals

**Goals:**
- Define a simple, thread-safe, in-memory rate limiter usable from both
  the webhook route and a `slack-bolt` middleware.
- Define exactly where in each existing request pipeline the rate-limit
  check happens.
- Define the minimal logging setup (format, `LOG_LEVEL` handling) this
  change needs, without building the full `overview.md` §5.5 Application
  Logging feature.

**Non-Goals:**
- The admin API for changing the log level at runtime — deferred.
- A distributed/shared rate limiter (Redis, etc.) — this is a
  single-process deployment; in-memory is sufficient and consistent with
  the project's "Simplicity" non-functional requirement.
- Exhaustive JSON log schema design for every future log line in the app
  — just what rate-limit violations and the existing authorization
  failures need.

## Decisions

### Rate limiter: a small, lock-guarded, fixed-window counter
Add `src/ratelimit.py: RateLimiter`, constructed with `max_requests` and
`window_seconds`, exposing `is_allowed(key: str) -> bool`. Internally, a
`dict[str, tuple[float, int]]` (key → `(window_start, count)`) guarded by
a single `threading.Lock()` — the same kind of cross-thread concern
`src/audit/db.py` already had to solve (`slack-bolt` dispatches on worker
threads; FastAPI handlers run async), so the lock is required for
correctness, not just defensiveness. A **fixed** window (reset the
counter once `window_seconds` has elapsed since it was last reset) rather
than a sliding one — simpler, and the known imprecision (up to roughly
2x the configured rate at a window boundary) is an acceptable trade-off
for abuse *mitigation*, not a hard security boundary. Two separate
`RateLimiter` instances get constructed in `src/main.py` — one per
`rate_limiting.discourse_webhook` / `rate_limiting.slack_commands` — since
they have independent thresholds and key spaces (IP vs Slack user ID).
Alternative considered: a shared generic limiter keyed by `(scope, key)`
tuples. Rejected — two small, independently-configured instances are
simpler to reason about and test than one limiter juggling two scopes.

### Discourse webhook: rate limit first, before signature verification
The rate-limit check happens as the very first step in
`create_webhooks_router()`'s handler — before reading the body for
signature verification. A flood of garbage requests shouldn't cost an
HMAC computation each; the rate limiter only needs the source IP, not the
body. Source IP is taken from the first address in `X-Forwarded-For` when
present (this service runs behind a reverse proxy/tunnel in every known
deployment — local dev via ngrok, and production via the Terraform-managed
infrastructure — so `request.client.host` would otherwise just be the
proxy, not the real source), falling back to `request.client.host` when
the header is absent. **Known limitation:** `X-Forwarded-For` is
attacker-controllable unless a trusted proxy strips/overwrites it before
forwarding — documented in Risks below, acceptable because rate limiting
here is abuse mitigation, not an authentication boundary (the HMAC
signature remains the actual authentication control, checked
immediately after).

### Slack commands: a global `slack-bolt` middleware, not per-handler checks
`slack-bolt`'s `App.use(middleware_func)` registers global middleware that
runs after Bolt's own signature verification but before any listener —
exactly the hook needed for "one shared check across all three commands"
without touching `_handle_trust`/`_handle_revoke`/`_handle_trust_status`
individually. The middleware reads `body["user_id"]`, checks it against
the shared `RateLimiter`, and on violation calls `ack(text="...")`
directly (confirmed `Ack.__call__` accepts `text` and sends it as both
the immediate HTTP response and a visible ephemeral Slack message in one
call) without calling `next()` — short-circuiting before any of the three
command handlers run. On success, it calls `next()` and the existing
handlers proceed unchanged. Alternative considered: per-command middleware
(`app.command("/trust", middleware=[...])` ×3). Rejected — the config
schema has one shared `slack_commands` limit, not three; a single global
middleware is the direct implementation of "shared counter across all
three."

### Logging: a small JSON formatter, configured once at startup
Add a `configure_logging()` call in `src/main.py` (or a tiny
`src/logging_setup.py` if it grows past a few lines) that calls
`logging.basicConfig` with a custom `logging.Formatter` subclass emitting
`{"timestamp", "level", "logger", "message"}` as JSON to stdout, and sets
the level from `LOG_LEVEL` (env var) falling back to `config.logging.level`
— the same "env var overrides config.yaml" pattern already used for
`DISCOURSE_REPLAY_WINDOW_SECONDS`. No new dependency (e.g.
`python-json-logger`) — a ~15-line formatter is simpler than adding and
pinning another package for this. `src/api/webhooks.py` and
`src/integrations/slack.py` each get a module-level
`logging.getLogger(__name__)` and call `.warning(...)` at the points
identified in the modified capability specs (signature/workflow-name
rejection, channel-restriction rejection, rate-limit rejection in both).

## Risks / Trade-offs

- **[Risk]** `X-Forwarded-For` can be spoofed by the client itself if no
  trusted proxy overwrites it. → **Mitigation:** acceptable as documented
  above — this is abuse mitigation layered in front of the real
  authentication control (HMAC signature), not itself a security boundary.
  Revisit if the production deployment's proxy configuration is confirmed
  to not sanitize this header.
- **[Risk]** The in-memory counters dict grows for as long as the process
  runs, with no eviction — unbounded for a pathological number of distinct
  keys. → **Mitigation:** not a real concern at this deployment's actual
  scale (one Discourse instance's requests, one Slack workspace's
  members) — noted as a known limitation rather than engineered around
  now.
- **[Risk]** Fixed-window counting allows up to ~2x the configured rate
  across a window boundary. → **Mitigation:** acceptable per Goals above;
  a sliding-window algorithm is a strict upgrade if this ever matters in
  practice, but adds complexity not justified by the current threat model.

## Migration Plan

Purely additive — no existing behavior changes for a request within the
configured limits. `config.yaml`'s `rate_limiting` block has been present
(and validated) since the original scaffolding, so no config migration is
needed; deployments already have valid values or `load_config()` would
already have been failing.
