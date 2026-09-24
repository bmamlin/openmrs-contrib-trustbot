## 1. Config loading

- [x] 1.1 Implement `src/config.py` with a `ServiceConfig` Pydantic model
      mirroring `config.yaml` (discourse/keycloak/slack/rate_limiting/
      logging/database/admin sections per
      `openspec/specs/config-schema.md`) and `load_config(path) ->
      ServiceConfig`; verify by loading `config/config.example.yaml` in a
      unit test and asserting `keycloak.realm == "OpenMRS"` and
      `database.path == "/data/audit.db"`.
- [x] 1.2 Add optional `CONFIG_PATH` / `RULES_PATH` entries to
      `.env.example`, defaulting to `/config/config.yaml` /
      `/config/rules.yaml` when unset, read by `src/config.py` and
      `src/engine/loader.py` respectively; verify a unit test shows
      setting `RULES_PATH` changes the path `load_rules()` reads from.

## 2. Rules engine core

- [x] 2.1 Add `TriggerEvent` and `ActionResult` models to
      `src/engine/models.py` per `design.md` - Decisions; verify
      `tests/unit/engine/test_models.py` covers valid construction and
      that `ActionResult.status` rejects a value outside
      `success`/`no_change`/`failure`.
- [x] 2.2 Implement `src/engine/loader.py: load_rules()` to read, parse,
      and validate `rules.yaml` into a `RuleSet`, re-reading from disk on
      every call (no caching); verify `tests/unit/engine/test_loader.py`
      loads `config/rules.example.yaml` successfully and picks up a
      change made to the file between two calls.
- [x] 2.3 Implement the `TRIGGER_MATCHERS` / `ACTION_EXECUTORS`
      type-keyed registries in `src/engine/evaluator.py`, populated by
      `src/triggers/__init__.py` and `src/actions/__init__.py` importing
      their concrete modules; verify a unit test asserts
      `"slack_trust_command"` and `"keycloak_add_groups"` are present in
      the registries after import.
- [x] 2.4 Implement `evaluate()` (OR-logic across a rule's triggers, skip
      `enabled: false` rules, return every matching enabled rule) and
      `execute_rule()` (dispatch via the registries, catch unexpected
      exceptions from an executor as a `failure` `ActionResult`, always
      call `src/audit/db.record_event()` for the attempted action) in
      `src/engine/evaluator.py`; verify
      `tests/unit/engine/test_evaluator.py` covers: a rule with two
      triggers matches on either one, a disabled rule never matches, two
      matching rules both execute for one event, and an executor
      exception is recorded as `failure` without stopping evaluation of
      other matched rules.

## 3. Audit log

- [x] 3.1 Implement `src/audit/db.py: get_connection()` (open the SQLite
      file at the configured path, applying `schema.sql` if `audit_log`
      doesn't exist yet) and `record_event()` (a single `INSERT`); verify
      `tests/unit/audit/test_db.py` (new directory) opens a temp-file DB,
      calls `record_event()` twice, and confirms two rows with the
      expected columns, and that no code path in the module issues
      `UPDATE`/`DELETE`.

## 4. Keycloak integration + action

- [x] 4.1 Implement `src/integrations/keycloak.py: KeycloakClient` on
      `python-keycloak`, with `get_user_groups()` (always queries live,
      never caches) and `add_user_to_groups()`, retrying exactly once
      after `keycloak.retry.retry_delay_seconds` on a connectivity
      failure before raising; verify
      `tests/unit/integrations/test_keycloak.py` (new directory) mocks
      the underlying client and asserts exactly one retry occurs before
      the call fails.
- [x] 4.2 Implement `src/actions/keycloak.py: add_groups()` returning an
      `ActionResult`: `no_change` if the user already has every target
      group, add only the missing groups otherwise (`success`), and
      `failure` with a message identifying the user if the OpenMRS ID
      doesn't exist in Keycloak; verify
      `tests/unit/actions/test_keycloak.py` covers all three outcomes
      against a mocked `KeycloakClient`.

## 5. Slack integration + trigger

- [x] 5.1 Implement `src/integrations/slack.py: create_slack_app()`
      building a `slack_bolt.App` with `signing_secret` / `bot_token`
      (from env vars) and a `/trust` command handler that acks
      immediately; verify a unit test confirms the returned `App` has a
      registered `/trust` command listener.
- [x] 5.2 Implement `src/triggers/slack.py` channel-restriction check
      (compare the command's channel ID against
      `slack.trusted_channel_id`) and `TriggerEvent` construction for
      `slack_trust_command`; verify
      `tests/unit/triggers/test_slack.py` covers: a command from the
      trusted channel builds a `TriggerEvent`, and a command from any
      other channel returns "rejected, no event" with no side effects.
- [x] 5.3 Wire the `/trust` command handler (in `src/integrations/slack.py`,
      calling into `src/triggers/slack.py`) to
      `src/engine/loader.load_rules()` + `evaluate()` + `execute_rule()`
      for each matched rule, then post the Slack response
      (confirmation / "already trusted" / user-not-found) per the
      `slack-trust-command` spec; verify
      `tests/integration/test_slack_trust_flow.py` (new) exercises the
      full path with mocked Keycloak and Slack clients for: a successful
      grant, a no-op grant, and an unknown OpenMRS ID.

## 6. FastAPI wiring

- [x] 6.1 In `src/main.py`, load `ServiceConfig` once at startup and
      construct the `KeycloakClient`, the Slack `App` /
      `SlackRequestHandler`, and the audit DB connection from it, storing
      them on `app.state`; mount the Slack request handler at
      `POST /slack/commands`; verify `uvicorn src.main:app` starts
      without error against `config/config.example.yaml` (with dummy env
      vars set) and `GET /health` still returns `200`.

## 7. Security-focused tests

- [x] 7.1 Add `tests/security/test_slack_trust_command.py` covering: a
      request with an invalid Slack signature is rejected before any
      Keycloak or audit call happens, and a validly-signed request from
      an unauthorized channel results in no rule-engine action and no
      visible Slack response, per the `slack-trust-command` spec's
      authorization requirements; verify the tests pass under `pytest`.

## 8. Docs

- [x] 8.1 Update `CLAUDE.md`'s Layout section to mention `src/config.py`
      and update its "Current state" note now that the Slack `/trust`
      path is implemented (no longer "`GET /health` is the one fully
      implemented endpoint"); verify by re-reading the file against the
      actual final module layout.

## 9. Full verification

- [x] 9.1 Run `pytest` and confirm every unit, integration, and security
      test added in this change passes; run `python -m py_compile` over
      all changed files under `src/`.
