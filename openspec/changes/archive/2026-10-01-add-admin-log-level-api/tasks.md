# Tasks

## 1. Shared log-level logic

- [x] 1.1 In `src/logging_setup.py`, add `VALID_LOG_LEVELS = {"DEBUG",
      "INFO", "WARNING", "ERROR"}` and `set_log_level(level: str) -> None`
      (uppercases, raises `ValueError` if not in `VALID_LOG_LEVELS`,
      otherwise `logging.getLogger().setLevel(level)`); refactor
      `configure_logging()` to validate the startup level through the
      same set (an invalid `LOG_LEVEL`/`config.logging.level` now raises
      at startup instead of silently passing through to stdlib
      `logging`); verify `tests/unit/test_logging_setup.py` gains cases
      for: a valid level change via `set_log_level()` takes effect
      immediately (assert via a subsequent log call and `capsys`), an
      invalid level raises `ValueError` and leaves the current level
      unchanged, and `configure_logging()` with an invalid level raises
      `ValueError` too.

## 2. Admin router

- [x] 2.1 In `src/api/admin.py`, replace the module-level `router` with
      `create_admin_router(*, admin_api_token: str, require_auth: bool)
      -> APIRouter` (factory + the router's own module docstring updated
      to drop "Not yet implemented"), implementing `POST
      /admin/log-level`: when `require_auth` is `True`, read the
      `Authorization` header, require `Bearer <token>` form, and compare
      with `hmac.compare_digest()` against `admin_api_token` — reject a
      missing/mismatched token with HTTP 401 before anything else; when
      `require_auth` is `False`, skip the check entirely. Then call
      `logging_setup.set_log_level(level)`, returning HTTP 400 (via
      `HTTPException`) if it raises `ValueError`, otherwise responding
      with the newly active level (e.g. `{"level": "<LEVEL>"}`).
- [x] 2.2 Add `logging.getLogger(__name__).warning(...)` for a rejected
      (401) request, identifying only that authorization failed — never
      the presented or configured token value.
- [x] 2.3 Create `tests/unit/api/test_admin.py` covering: valid token
      (or `require_auth=False`) + valid level changes the level and
      returns it in the response; valid token + invalid level name
      returns 400 and leaves the level unchanged; missing
      `Authorization` header returns 401; wrong token returns 401;
      `require_auth=False` allows the request through with no
      `Authorization` header at all; a 401 rejection logs a WARNING that
      does not contain the configured token or any attempted token value
      (via `caplog`).

## 3. Wiring

- [x] 3.1 In `src/main.py`, read `ADMIN_API_TOKEN` via
      `os.environ.get("ADMIN_API_TOKEN", "")`; if
      `config.admin.require_auth` is `True` and the token is blank,
      raise a clear startup error (fail fast, matching the existing
      pattern for required secrets like `SLACK_BOT_TOKEN`); otherwise
      pass the token and `config.admin.require_auth` into
      `admin.create_admin_router(...)`, replacing the current
      `app.include_router(admin.router)` call; verify
      `tests/unit/test_main.py` still passes and `GET /health` still
      returns 200.
      Also add a case there (or alongside) confirming the app fails to
      start when `admin.require_auth` is `True` (the config default) and
      `ADMIN_API_TOKEN` is unset/blank.

## 4. Security-focused test

- [x] 4.1 Add `tests/security/test_admin_log_level.py`, exercising `POST
      /admin/log-level` through the real app (`src.main`, mirroring the
      other `tests/security/` fixtures): a request with no token is
      rejected (401) and the subsequent `GET /health` behavior is
      unaffected; a request with a valid token and a recognized level
      succeeds; a request with a valid token and an unrecognized level
      is rejected (400).

## 5. Docs

- [x] 5.1 Update `CLAUDE.md`'s "Current state" note: move the admin
      log-level API from "remains a stub" to implemented, leaving
      dry-run mode as the one remaining stub; verify by re-reading the
      file against the actual final behavior.

## 6. Full verification

- [x] 6.1 Run `pytest` and confirm every unit, integration, and security
      test — old and new — passes; run `python -m py_compile` over all
      changed files under `src/`.
