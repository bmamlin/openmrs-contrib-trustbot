# Design

## Context

`src/api/admin.py` already mounts an `APIRouter(prefix="/admin")` with a
stubbed `POST /admin/log-level` that raises `NotImplementedError`, included
in the FastAPI app in `src/main.py` alongside `health` and `webhooks`.
`src/logging_setup.py: configure_logging()` already sets the root logger's
level once at startup (`LOG_LEVEL` env var, falling back to
`config.logging.level`) with a JSON formatter. `config.yaml`'s `AdminConfig`
(`src/config.py`) already has `require_auth: bool = True`; `ADMIN_API_TOKEN`
is documented in `config-schema.md` as an env var but nothing reads it yet.
See proposal.md for why this is needed.

The project's established pattern for a router that needs per-instance
config (secrets, feature flags) is a factory function returning the
configured `APIRouter`, constructed once in `src/main.py` — see
`webhooks.create_webhooks_router()` and `integrations.slack.create_slack_app()`.
This change follows the same shape for `admin.py`.

## Goals / Non-Goals

**Goals:**
- Implement `POST /admin/log-level` per the new `admin-log-level-api` spec.
- Share the actual level-setting logic with `configure_logging()` so
  startup and runtime use one code path, not two.
- Keep the bearer-token check simple and consistent with how the rest of
  the codebase handles comparable secrets (constant-time comparison, like
  the Discourse webhook's HMAC check in `src/api/webhooks.py`).

**Non-Goals:**
- No new persistence for the log level — it is process-local, in-memory
  state (the root logger's level), same as today. A restart still reverts
  to the configured startup level; that's expected and not addressed here.
- No general-purpose auth framework — this is a single bearer-token check
  for a single low-traffic internal endpoint, not a reusable
  authentication layer for future admin endpoints (revisit if/when a
  second admin endpoint is added).
- No change to `admin.port` (`AdminConfig.port`, currently unused — the
  whole app already runs as one FastAPI process on one uvicorn port, so
  there is no separate "admin port" to bind). Out of scope for this change.

## Decisions

### Share level-setting logic via `src/logging_setup.py: set_log_level()`
Add `VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}` and
`set_log_level(level: str) -> None` to `src/logging_setup.py`, raising
`ValueError` for anything not in that set, otherwise calling
`logging.getLogger().setLevel(level)`. `configure_logging()` is refactored
to validate through the same set (so an invalid `LOG_LEVEL`/`config.yaml`
value now fails the same way at both startup and runtime, rather than
silently passing an unrecognized string to stdlib `logging`, which would
otherwise accept it at `WARNING`-equivalent effective behavior with no
error). The admin route catches `ValueError` and turns it into HTTP 400.
Alternative considered: duplicate the validation in `admin.py`. Rejected —
one validated set of level names, in the module that owns logging setup.

### Factory function + context dataclass, matching webhooks/slack
`src/api/admin.py` gets `create_admin_router(*, admin_api_token: str,
require_auth: bool) -> APIRouter`, constructed in `src/main.py` and
included via `app.include_router(...)`, replacing the current
parameterless `router` module-level object. Mirrors
`create_webhooks_router()`/`create_slack_app()` exactly — same rationale
(per-instance config without global state).

### Bearer-token check: inline, constant-time, skippable via config
The route reads the `Authorization` header, expects `Bearer <token>`, and
compares with `hmac.compare_digest()` against the configured
`admin_api_token` — the same pattern `src/api/webhooks.py: _verify_signature()`
already uses for the Discourse HMAC check. When `require_auth` is `False`,
the check is skipped entirely (no header inspection at all), matching the
spec's "Authorization disabled" scenario. Alternative considered: FastAPI's
`HTTPBearer` security dependency. Rejected — it would be the only use of
`fastapi.security` in the codebase for a single endpoint; the inline check
is simpler and consistent with the existing webhook signature style.

### Fail fast at startup if auth is required but no token is configured
In `src/main.py`, `ADMIN_API_TOKEN` is read via
`os.environ.get("ADMIN_API_TOKEN", "")`. If `config.admin.require_auth` is
`True` (the default) and the token is blank, startup fails immediately
with a clear error, the same fail-fast posture the project already uses
for required secrets like `SLACK_BOT_TOKEN` (`os.environ["SLACK_BOT_TOKEN"]`
raises `KeyError` immediately when absent) — an admin endpoint that can
never successfully authenticate is a misconfiguration, not a valid
deployment state. When `require_auth` is `False` (non-production/dev), a
blank token is fine since the check is skipped.

### Never logging the token
The only places the token value could leak are the `Authorization` header
itself and the configured `admin_api_token`. The route never logs the raw
header value; a rejection log line names only that authorization failed
(mirroring the existing channel-restriction and rate-limit WARNING log
lines added in `add-rate-limiting` — identify *what* was rejected, never
echo the credential itself).

## Risks / Trade-offs

- **[Risk]** A deployment sets `require_auth: false` outside of
  local/dev and exposes an unauthenticated log-level-change endpoint. →
  **Mitigation:** `require_auth` already defaults to `true`, and
  `config-schema.md` already documents "Always set to true in
  production" — this change doesn't alter that guidance, just implements
  the enforcement.
- **[Risk]** Log level reverts to the startup value on every restart/
  redeploy, which could surprise an operator who set DEBUG for an
  investigation and forgot. → **Mitigation:** acceptable and expected —
  this is explicitly in-memory, process-local state per Non-Goals; a
  response confirming the newly active level gives the operator
  immediate feedback, and reverting on restart is the safer default
  (DEBUG logging left on indefinitely risks leaking more verbose data).

## Migration Plan

Purely additive — the route already exists but always raised
`NotImplementedError`, so there is no prior working behavior to migrate
away from. No config schema changes (`admin.require_auth` already exists
and defaults `true`; `ADMIN_API_TOKEN` was already documented, just
unused until now).
