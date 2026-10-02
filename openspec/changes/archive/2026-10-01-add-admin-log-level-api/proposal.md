# Proposal

## Why

The application log level is currently fixed at process startup (`LOG_LEVEL`
env var or `config.yaml`'s `logging.level`, read once by `configure_logging()`
in `src/main.py`). Diagnosing an intermittent production issue — a flaky
Keycloak connection, an unexpected Discourse payload — means restarting the
service into DEBUG and hoping to reproduce the issue again, rather than
turning up verbosity on the already-running process. Per `overview.md` §5.5,
the service needs a protected admin endpoint that changes the running
log level without a restart. The route and its `NotImplementedError` stub
already exist (`src/api/admin.py: POST /admin/log-level`); this proposes the
spec and implementation to back it.

## What Changes

- Implement `POST /admin/log-level` to change the running process's log
  level (DEBUG | INFO | WARNING | ERROR) at runtime, reusing the root
  logger `configure_logging()` already configures.
- Require a valid `ADMIN_API_TOKEN` bearer token on this endpoint
  whenever `config.yaml`'s `admin.require_auth` is `true` (the default);
  reject missing/invalid tokens with HTTP 401 before changing anything.
- Reject an unrecognized level name with HTTP 400 and leave the current
  level unchanged.
- Never log the admin token itself, at any level.

## Capabilities

### New Capabilities
- `admin-log-level-api`: runtime log-level control via a protected admin
  endpoint — request authorization, valid-level acceptance, invalid-level
  rejection, and the logging/secrecy constraints around it.

### Modified Capabilities
(none — this is new, additive behavior on an existing but unimplemented
route; no existing capability's requirements change)

## Impact

- `src/api/admin.py`: implement `set_log_level()` (currently
  `NotImplementedError`); add the bearer-token check.
- `src/logging_setup.py`: likely add a small `set_log_level()` helper
  (validate + apply) so the admin route and the startup path share the
  same level-setting logic.
- `src/main.py`: thread `ADMIN_API_TOKEN` (env var) and
  `config.admin.require_auth` into the admin router (same
  factory-function wiring pattern already used for `create_webhooks_router`
  and `create_slack_app`).
- `tests/unit/api/test_admin.py` (new), plus a `tests/security/` case for
  missing/invalid-token rejection.
